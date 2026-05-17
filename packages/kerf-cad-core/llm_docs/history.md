# Parametric History DAG — `geom/history/`

Four-module subsystem that makes the kerf kernel *parametric*: feature edits
propagate through a dependency graph without breaking downstream topology
references.

Modules:
- `feature.py` — the `Feature` data model and `PersistentSelector`
- `persistent_naming.py` — face/edge/vertex stable IDs + `NamingTable`
- `dag.py` — `FeatureDAG` orchestration
- `evaluators.py` — concrete feature kinds (Box, Cylinder, Sphere, Boolean,
  Chamfer, Fillet) with their naming-table builders

---

## Why it exists

When a user fillets the top-front edge of a box and later changes the box's
`dx` from 2 to 4, the fillet must re-apply to the **same topological edge** of
the now-larger box — not a random edge, and not crash. The history DAG +
persistent naming make this possible.

---

## `feature.py` — Feature model

### `Feature`

The unit of the DAG. Fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | UUID4 hex — stable across re-evaluations and serialise/deserialise |
| `kind` | str | Evaluator dispatch key, e.g. `"box"`, `"chamfer_edge"` |
| `inputs` | dict | Named refs to upstream features (`FeatureRef`) or selectors (`PersistentSelector`) |
| `params` | dict | Scalar parameters — the editable surface |
| `outputs` | dict | Last-evaluated outputs; `outputs["body"]` is the canonical `Body` |
| `naming_table` | Any | Last-evaluated `NamingTable` from the evaluator |

Serialisation: `Feature.to_dict()` / `Feature.from_dict(d)`.
Round-trip safe; `outputs` and `naming_table` are not serialised (derived state).

### `FeatureRef`

Reference to a named output of an upstream feature.

```python
FeatureRef(feature_id: str, output_name: str = "body")
```

### `PersistentSelector`

A reference to a face / edge / vertex of an upstream feature's output,
resolvable across regenerations.

```python
PersistentSelector(feature_id: str, entity_kind: str, role: str)
# entity_kind: "face" | "edge" | "vertex"
# role: structural tag, e.g. "+X", "rim_top", "A:+Y", "bevel:+X/-Z#0"
```

`MissingReferenceError` is raised when a selector cannot be resolved (the role
no longer exists after a parameter change or kind replacement).

---

## `persistent_naming.py` — Stable IDs

### Algorithm

A persistent ID has three parts packed as `feature_id::role::fingerprint`:

1. **`feature_id`** — UUID4 of the producing feature (pins to the DAG node).
2. **`role`** — structural label assigned by the evaluator; purely structural,
   never encodes numeric values. Examples:
   - Box: `face:+X`, `edge:+Y/+Z`, `vertex:+X/+Y/-Z`
   - Cylinder: `face:lateral`, `edge:rim_bottom`, `edge:seam`
   - Boolean: `face:A:+X`, `face:B:lateral`, `face:boundary:0`
   - Chamfer: `face:bevel:+Y/+Z#0`
   - Fillet: `face:fillet:+Y/+Z`
3. **`fingerprint`** — 12-char SHA-256 of (centroid, normal, area/length),
   rounded to fixed precision. Used only as a tie-breaker for kind-change
   detection, not for normal identity.

### Resolution

`PersistentSelector(feature_id, role)` resolves against a live `Body` by
looking up the producing feature's current `NamingTable` and returning the
live `Face`/`Edge`/`Vertex` registered under `role`. If the role is absent,
`MissingReferenceError` is raised with the persistent ID and available roles.

### `NamingTable`

Per-feature role → live-entity map, rebuilt on every evaluation.

```python
table = NamingTable(feature_id="...")
pid = table.register_face("+X", some_face)   # returns PersistentId
pid = table.register_edge("rim_top", edge)
pid = table.register_vertex("+X/+Y/+Z", v)

table.face_roles()    # sorted list of registered face roles
table.edge_roles()    # sorted list of edge roles
table.all_roles()     # {"face": [...], "edge": [...], "vertex": [...]}
```

### Role-inference helpers

```python
face_role_for_box_planar(face)              # → "+X" / "-Y" / None
edge_role_for_box(edge, incident_face_roles)# → "+Y/+Z" / None
vertex_role_for_box(point, box_centroid)    # → "+X/+Y/-Z"
```

---

## `dag.py` — FeatureDAG

### Construction and population

```python
from kerf_cad_core.geom.history.dag import FeatureDAG

dag = FeatureDAG()
dag.register_evaluator("box", my_box_evaluator)
dag.add_feature(some_feature)   # raises DAGCycleError if cycle detected
```

### Edit verbs

```python
dag.set_param(feature_id, "dx", 4.0)          # mutate a param + invalidate downstream
dag.link(downstream_id, "edge", new_selector)  # re-wire an input
dag.replace_feature_kind(fid, "cylinder", {...})  # kind swap
```

### Evaluation

```python
body = dag.evaluate(feature_id)   # evaluate one node, reuse cache upstream
dag.regenerate()                  # re-evaluate all invalidated features in topo order
dag.regenerate([changed_id])      # explicitly invalidate + regenerate
```

### Selector resolution

```python
entity = dag.resolve_selector(selector)   # raises MissingReferenceError if gone
table  = dag.naming_table(feature_id)     # NamingTable for a feature
```

### Serialisation

```python
d = dag.to_dict()                   # list of feature dicts; no caches
dag2 = FeatureDAG.from_dict(d, evaluators={"box": ev, ...})
dag2.regenerate()                   # rebuild caches
```

### `DAGCycleError`

Raised by `add_feature` and `link` if a cycle would be created.
`.cycle_path` contains the cycle as a list of feature ID strings.

---

## `evaluators.py` — Built-in feature kinds

### Helper constructors

```python
BoxFeature(corner, dx, dy, dz, *, tol=1e-7)
CylinderFeature(axis_pt, axis_dir, radius, height, *, tol=1e-7)
SphereFeature(centre, radius, *, tol=1e-7)
BooleanFeature(op, a: FeatureRef, b: FeatureRef, *, tol=1e-6)
# op: "union" | "difference" | "intersection"
ChamferEdgeFeature(body: FeatureRef, edge: PersistentSelector, width, *, tol=1e-6)
FilletEdgeFeature(body: FeatureRef, edge: PersistentSelector, radius, *, tol=1e-6)
```

### `register_default_evaluators(dag)`

Registers all six built-in evaluators on a `FeatureDAG`.

### Role tagging per kind

| Kind | Face roles | Edge roles |
|------|-----------|-----------|
| `box` | `+X/-X/+Y/-Y/+Z/-Z` | `+A/+B` (sorted face pairs) |
| `cylinder` | `lateral`, `cap_bottom`, `cap_top` | `rim_bottom`, `rim_top`, `seam` |
| `sphere` | `surface` | `seam` |
| `boolean` | `A:<role>`, `B:<role>`, `boundary:<idx>` | sorted face-pair |
| `chamfer_edge` | inherited + `bevel:<edge_role>#<idx>` | sorted face-pair |
| `fillet_edge` | inherited + `fillet:<edge_role>` | sorted face-pair |

---

## Worked DAG example

```
box_feat ──────────────────────────────────────┐
  kind="box", dx=2, dy=2, dz=4               face:+Z = top face
                                               edge:+X/+Z = one top edge
                                               ↓
                                        chamfer_feat
                                          kind="chamfer_edge"
                                          edge = PersistentSelector(box_feat.id, "edge", "+X/+Z")
                                          width = 0.3
                                               ↓
                                        fillet_feat
                                          kind="fillet_edge"
                                          edge = PersistentSelector(box_feat.id, "edge", "+Y/+Z")
                                          radius = 0.5
```

1. `dag.add_feature(box_feat)` → no upstreams, evaluated on first `evaluate`.
2. `dag.add_feature(chamfer_feat)` → upstream = `box_feat`.
3. `dag.add_feature(fillet_feat)` → upstream = `box_feat`.
4. `dag.regenerate()` → evaluates in topo order: box → chamfer → fillet.
5. `dag.set_param(box_feat.id, "dx", 4.0)` → invalidates box + chamfer + fillet.
6. `dag.regenerate()` → re-evaluates all three; the chamfer and fillet re-resolve
   their `PersistentSelector` against the box's regenerated `NamingTable` and
   find the same structural roles on the larger box.

---

## Notes

- Cycle detection uses Kahn's algorithm; tie-breaking by insertion order for
  determinism.
- `evaluate_with_counter(feature_id)` returns `(body, call_counts)` where
  `call_counts[fid]` is `> 0` only for features actually re-evaluated (not
  served from cache). Useful for testing that cache hit rates are correct.
- `MissingReferenceError` is importable from both `feature.py` and
  `persistent_naming.py` for convenience.
- The evaluator callable signature is
  `(feature: Feature, ctx: EvaluationContext) -> EvaluationResult`.
  `EvaluationContext.resolve_selector(selector)` is the canonical way to
  obtain a live `Face`/`Edge`/`Vertex` inside an evaluator.
