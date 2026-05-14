# Authoring `.feature` files

A `.feature` file is the OCCT B-rep timeline: a JSON tree of typed
operations. The frontend's occtWorker evaluates the tree to a precise
B-rep solid.

Scaffold one with `create_feature` (returns a blank tree). After that,
edit by appending or modifying nodes via `write_file` / `edit_file`.

## File shape

```json
{
  "version": 1,
  "name": "bracket",
  "features": [
    { "id": "pad-1",    "op": "pad",    "sketch_path": "/profile.sketch",
      "height": 10, "direction": "up" },

    { "id": "pocket-1", "op": "pocket", "target_id": "pad-1",
      "sketch_path": "/slot.sketch", "depth": 4 },

    { "id": "fillet-1", "op": "fillet", "target_id": "pocket-1",
      "edge_filter": "all", "radius": 1 }
  ],
  "metadata": {}
}
```

The `features` array is ordered — each node's `target_id` references an
earlier node by `id`. The last node is the result body.

Standard `id` style is `<op>-<n>` (e.g. `pad-1`, `fillet-3`). Pick any
unique short id — readability matters more than a specific scheme.

## Operations

### `pad` — linear extrude

```json
{
  "id":  "pad-1",
  "op":  "pad",
  "sketch_path": "/base.sketch",
  "height": 10,
  "direction": "up"          // "up" | "down" | "symmetric"
}
```

Extrudes the closed loop in the sketch by `height` mm. `symmetric`
extrudes ±height/2 about the sketch plane.

### `pocket` — subtractive extrude

```json
{
  "id":  "pocket-1",
  "op":  "pocket",
  "target_id":   "pad-1",
  "sketch_path": "/slot.sketch",
  "depth": 4
}
```

Cuts the closed loop down by `depth` mm into the body of `target_id`.

### `revolve` — rotate around world axis

```json
{
  "id":  "rev-1",
  "op":  "revolve",
  "sketch_path": "/profile.sketch",
  "axis": "y",         // "x" | "y" | "z"
  "angle_deg": 360
}
```

Sweeps the closed loop around the axis. `0 < angle_deg ≤ 360`.

### `fillet` — round edges

```json
{
  "id":  "fil-1",
  "op":  "fillet",
  "target_id": "pad-1",
  "edge_filter": "all",   // "all" | "horizontal" | "vertical" | "manual"
  "radius": 1.5,
  "edge_ids": [3, 7]      // only when edge_filter = "manual"
}
```

`edge_filter`:
- `all` — round every edge in the body.
- `horizontal` / `vertical` — only edges that are axis-aligned along
  that axis after evaluation.
- `manual` — pick by post-eval edge index (NOT stable across feature
  edits in v1; usable for UI-driven authoring only).

### `chamfer` — bevel edges

```json
{
  "id":  "cha-1",
  "op":  "chamfer",
  "target_id": "pad-1",
  "edge_filter": "all",   // same vocabulary as fillet
  "distance": 0.5,
  "edge_ids": []
}
```

### `shell` — hollow

```json
{
  "id":  "shl-1",
  "op":  "shell",
  "target_id": "pad-1",
  "thickness": 1.5,
  "face_ids": []   // empty = remove top-Z face by default
}
```

### `hole` — drill

```json
{
  "id":  "hol-1",
  "op":  "hole",
  "target_id": "pad-1",
  "sketch_path": "/holes.sketch",
  "diameter": 3,
  "depth": 8
}
```

Drills a `diameter × depth` cylinder at the first non-origin point in
the referenced sketch.

### `linear_pattern` — copy along an axis or edge

```json
{
  "id":  "lp-1",
  "op":  "linear_pattern",
  "direction": "x",       // "x" | "y" | "z" | <edge_id> (number)
  "count": 5,
  "spacing": 12
}
```

Translates the current body `count` times along `direction × spacing` and
fuses the copies. `direction` accepts a world axis name or a numeric edge id
(stable only within the current evaluation — see "edge_id stability" below).
Phase 3 v1 always patterns the *current body* — multi-body patterns are
Phase 4.

### `polar_pattern` — copy around an axis

```json
{
  "id":  "pp-1",
  "op":  "polar_pattern",
  "axis": "z",            // "x" | "y" | "z" | <edge_id>
  "count": 6,
  "total_angle_deg": 360
}
```

Rotates the current body `count` times around the axis and fuses. For
`total_angle_deg = 360`, copies are evenly distributed across the full
circle (count slots); for partial angles, copies span `[0, total_angle_deg]`
inclusive of both ends.

### `mirror_pattern` — copy across a plane

```json
{
  "id":  "mp-1",
  "op":  "mirror_pattern",
  "plane": "xy"           // "xy" | "xz" | "yz" | <face_id>
}
```

Mirrors the current body across the world plane or the specified planar
face, then fuses the original and the mirror.

### `push_pull` — direct-modeled face extrusion

```json
{
  "id":  "pp-1",
  "op":  "push_pull",
  "face_id": 7,
  "distance": 5
}
```

Extrudes the planar face `face_id` along its outward normal by `distance` mm
and fuses the result onto the body (positive distance) or cuts (negative
distance). Created by the Push/Pull tool in the Feature editor — drag a
face along its normal, release to commit.

`face_id` is the post-evaluation face index from the OCCT worker's TopExp
order. It is **not stable across structural feature edits**: adding,
removing, or reordering features will renumber faces. The push_pull node
captures the id at click time; if the upstream tree is later edited, the
node may bind to a different face on re-evaluation. Treat push_pull as a
"snapshot" op rather than a parametric one.

## Edge / face id stability

The OCCT worker assigns sequential numeric ids to every face and edge in
TopExp explorer order on each evaluation. This means:

- Re-running the same FeatureTree → same ids (deterministic).
- Pure parameter tweaks (changing `height`, `radius`, etc.) → same ids
  (topology is preserved).
- Structural edits (add/remove/reorder features) → ids shuffle. Manual
  `edge_ids` / `face_ids` references may bind to different geometry.

Phase 3 doesn't solve persistent naming — the UI clears the viewport
selection on structural edits and surfaces a "Selections may reset" hint.
Phase 4 will add a soft-persistence layer that remaps ids by spatial
proximity to keep "intent" alive across edits.

## Validation rules

- Every `target_id` must reference an earlier node's `id`.
- Every `sketch_path` must point to an existing `.sketch` file.
- Numeric scalars (`height`, `radius`, `thickness`, `depth`, `distance`,
  `diameter`, `angle_deg`, `spacing`) must be > 0 (except push_pull's
  `distance`, which can be negative for inward cuts).
- Pattern `count` must be ≥ 2.
- `version` stays `1`.

## Future ops (Rhino-tier; Phase 4 — not yet evaluated)

These nodes parse but the worker rejects them today; reserved for the
NURBS surfacing phase:
- `sweep1` — sweep one rail along one profile.
- `sweep2` — sweep two rails along one profile.
- `networkSrf` — surface from a network of curves.
- `blendSrf` — G1/G2 blend between two surfaces.
- `matchSrf` — match an edge of one surface to another with continuity.

## Common edits

Add a fillet to an existing tree (the `pad-1` body):

1. `read_file('/bracket.feature')` — discover existing ids.
2. `edit_file('/bracket.feature', '"features": [\n', '"features": [\n    {"id": "fil-1", "op": "fillet", "target_id": "pad-1", "edge_filter": "all", "radius": 1},\n')`

Or append at the end (which is usually correct, since features are
ordered top-to-bottom):

```text
edit_file: replace
  ]
}
with
    {"id": "fil-1", "op": "fillet", "target_id": "pad-1", "edge_filter": "all", "radius": 1}
  ]
}
```

(Watch the trailing-comma placement — JSON is strict.)
