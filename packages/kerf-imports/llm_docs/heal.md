# kerf-imports · heal.py

Triangle mesh healing pipeline and watertight validation.

## Entrypoints

### `heal(model, tolerance=1e-4) -> dict`

8-step mesh healing pipeline. Returns `{model, report}`.

```python
from kerf_imports.heal import heal

result = heal(model, tolerance=1e-4)
healed_model = result["model"]
report = result["report"]
# report keys: steps_run, vertices_merged, slivers_removed,
#              tiny_edges_merged, normals_flipped, holes_filled, warnings
```

Pipeline steps (in order):

1. **Vertex merge** — weld vertices within `tolerance` using spatial hashing.
2. **Degenerate face removal** — remove zero-area triangles (area < tolerance²).
3. **Sliver removal** — remove triangles with aspect ratio > threshold.
4. **Tiny-edge merge** — collapse edges shorter than `tolerance`.
5. **Duplicate face removal** — remove topologically identical faces.
6. **Normal unification** — BFS orientation propagation (see below).
7. **Hole filling** — fan-triangulate boundary loops up to 20 edges.
8. **Validation** — check watertightness and report remaining issues.

### `_unify_normals(mesh)`

BFS from the seed face with the largest positive-Z normal component.
Propagates consistent outward orientation: if a shared edge between two
faces has the same directed half-edge in both (co-directed), one face is
flipped.

### `_fill_holes(mesh, tolerance)`

Identifies boundary edge loops (edges belonging to exactly one face).
Loops with ≤ 20 edges are filled by fan triangulation: a centroid vertex
is added at the loop centroid, then triangles fan from it to each boundary
edge.

### `validate_watertight(mesh) -> dict`

```python
from kerf_imports.heal import validate_watertight

v = validate_watertight(mesh)
# v: {watertight, euler_characteristic, boundary_edge_count,
#     non_manifold_edge_count, warnings}
```

Checks:
- **Euler characteristic** V − E + F == 2 (genus-0 closed surface)
- **No boundary edges** (edges shared by exactly one face)
- **No non-manifold edges** (edges shared by more than two faces)

### `step_ap242_metadata(step_text) -> dict`

Regex-based metadata extractor for STEP AP242 files.

```python
from kerf_imports.heal import step_ap242_metadata

meta = step_ap242_metadata(step_content)
# meta: {file_schema, products, geometric_tolerances,
#         pmi_items, assembly_usages, warnings}
```

Extracts: `FILE_SCHEMA`, `PRODUCT`, `GEOMETRIC_TOLERANCE`,
`PMI_REPRESENTATION_ITEM`, `NEXT_ASSEMBLY_USAGE_OCCURRENCE`.

## LLM tools

| Tool | Write | Description |
|---|---|---|
| `heal_mesh` | yes | Run the 8-step healing pipeline on a mesh file |
| `validate_watertight` | no | Check Euler characteristic and manifoldness |
| `step_ap242_metadata` | no | Extract GD&T/PMI metadata from a STEP file |
| `interop_report` | no | Combined heal + validate + metadata report |

## Standards reference

- ISO 10303-242: STEP AP242 Managed model-based 3D engineering
- ASME Y14.41-2019: Digital Product Definition Data Practices (PMI)
