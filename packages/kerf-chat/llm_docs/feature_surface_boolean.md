# `feature_surface_boolean` — surface-direct CSG boolean

Appends a `surface_boolean` node to a `.feature` file. Performs a
constructive-geometry operation between two feature bodies without requiring
either operand to be a solid: `cut` (A − B), `fuse` (A ∪ B), or `common`
(A ∩ B).

**This is the surface-direct path.** Unlike [`feature_boolean`](./feature_boolean.md),
which wraps `BRepAlgoAPI_Cut/Fuse/Common` on `TopoDS_Solid` operands, this
op accepts `TopoDS_Face`, `TopoDS_Shell`, `TopoDS_Compound`, and
`TopoDS_Solid` shapes equally. The result is a `TopoDS_Compound` of trimmed
face fragments rather than a closed solid. The renderer walks the compound
via `TopExp_Explorer` the same as any other compound — no additional step
needed to display the result.

**When to use `feature_surface_boolean` vs `feature_boolean`:**

| Situation | Recommended tool |
|-----------|-----------------|
| Both bodies are sweeps, blends, or network surfaces | `feature_surface_boolean` |
| Solid-solid boolean (pads, revolves, boss features) | `feature_boolean` |
| You want to avoid the `feature_to_solid` tolerance step | `feature_surface_boolean` |
| The worker returns a BOPAlgo error mentioning C1-T10 | Fall back to `feature_boolean` + `feature_to_solid` (current WASM build limitation) |

## Schema

```json
{
  "id": "surface_boolean-1",
  "op": "surface_boolean",
  "target_a_id": "blend_srf-1",
  "target_b_id": "sweep1-2",
  "kind": "cut",
  "fuzziness": 1e-4
}
```

### Parameters

| Parameter      | Type          | Required | Default | Notes                                                             |
|----------------|---------------|----------|---------|-------------------------------------------------------------------|
| `file_id`      | string (uuid) | yes      | —       | Target `.feature` file id                                         |
| `target_a_id`  | string        | yes      | —       | First operand — preserved body on cut; first union body on fuse   |
| `target_b_id`  | string        | yes      | —       | Second operand — tool body on cut                                 |
| `kind`         | string (enum) | yes      | —       | `"cut"`, `"fuse"`, or `"common"`                                  |
| `fuzziness`    | number        | no       | 1e-4    | Intersection tolerance in model units. Raise to 1e-3 if tangent-intersection fragments go missing. |
| `options.id`   | string        | no       | auto    | Explicit node id (`"surface_boolean-N"`)                          |

### `kind` values

| Value      | Operation | Notes                                                                 |
|------------|-----------|-----------------------------------------------------------------------|
| `"cut"`    | A − B     | Subtracts B from A; returns face fragments of A outside B             |
| `"fuse"`   | A ∪ B     | Union of A and B as a compound of face patches                        |
| `"common"` | A ∩ B     | Intersection — only overlapping face region is kept                   |

## Worked examples

### 1. Cut a blend surface with a sweep (jewelry shank window)

```json
[
  { "id": "shank",       "op": "sweep1",      "profile_sketch_path": "/shank_profile.sketch", "path_sketch_path": "/shank_path.sketch" },
  { "id": "cutter",      "op": "sweep1",      "profile_sketch_path": "/window.sketch",         "path_sketch_path": "/window_path.sketch" },
  { "id": "sb-1",        "op": "surface_boolean", "target_a_id": "shank", "target_b_id": "cutter", "kind": "cut" }
]
```

### 2. Fuse a network surface with a blend

```json
[
  { "id": "net-1",  "op": "network_srf",  "u_sketch_paths": ["/u1.sketch", "/u2.sketch"], "v_sketch_paths": ["/v1.sketch"] },
  { "id": "blend-1","op": "blend_srf",    "target_id": "net-1", "edge1_id": 1, "edge2_id": 3 },
  { "id": "sb-1",   "op": "surface_boolean", "target_a_id": "net-1", "target_b_id": "blend-1", "kind": "fuse" }
]
```

### 3. Tangent-intersection case — raise fuzziness

If the two surfaces are nearly tangent at their intersection seam and the
result is missing face fragments, raise `fuzziness` to 1e-3:

```json
{ "id": "sb-1", "op": "surface_boolean", "target_a_id": "a", "target_b_id": "b", "kind": "cut", "fuzziness": 1e-3 }
```

## Binding coverage and honesty

This op uses `BRepAlgoAPI_Cut_3 / Fuse_3 / Common_3` — the same classes as
`feature_boolean` — but passes Face/Shell operands. The C++ API accepts any
`TopoDS_Shape`; the JS binding may or may not enforce solid types at the
TS-narrowing level. The worker surfaces a clear error with a **C1-T10
escalation** note if the binding refuses non-solid operands. In that case,
fall back to `feature_to_solid` + `feature_boolean`.

Optional improvements applied when bindings are present (verified at boot via
`[occt-phase4]` console log):
- **`ShapeFix_Shape` pre-pass** — softens tolerance inconsistencies in raw NURBS operands.
- **`SetFuzzyValue`** — sets intersection fuzziness on the underlying `BOPAlgo_Builder` (if callable).
- **`ShapeUpgrade_UnifySameDomain`** — merges co-planar/co-cylindrical face fragments in the result.

## Error messages

| Message | Cause |
|---------|-------|
| `surface_boolean: target_a 'X' not found in evaluated tree` | `target_a_id` refers to a node that hasn't been evaluated yet (wrong order) |
| `surface_boolean: cut algorithm failed (BOPAlgo error). … C1-T10` | OCCT boolean failed; binding may not accept non-solid operands — try `feature_boolean` + `feature_to_solid` |
| `surface_boolean: cut produced an empty result` | Operands do not intersect; check their positions |
| `surface_boolean: unknown kind 'foo'` | `kind` must be `"cut"`, `"fuse"`, or `"common"` |
