# feature_section — Plane Cross-Section of a Solid

Append a `section` node to a `.feature` file.  Intersects a solid body with a plane using
OCCT `BRepAlgoAPI_Section` and stores the resulting edge compound (2-D cross-section
outline) as a `.section` file.

---

## When to use

Keywords: section, cross-section, plane cut, slice solid, 2D outline, section view,
BRepAlgoAPI_Section, OCCT section, feature section, cut plane, sectional view, DXF
cross-section, part section.

---

## Entrypoints

### `validate_section_args(target_solid_ref, plane) -> tuple[str|None, str|None]`

Pure validation.  Returns `(error_msg, error_code)` or `(None, None)`.

---

### `build_section_node(node_id, target_solid_ref, plane_point, plane_normal, name) -> dict`

Build the feature-node dict:
```json
{
  "id": "section-1",
  "op": "section",
  "target_solid_ref": "pad-1",
  "plane": {
    "point":  [0.0, 0.0, 10.0],
    "normal": [0.0, 0.0, 1.0]
  }
}
```

---

## LLM tool

**Name:** `feature_section`

**Required args:** `file_id` (UUID), `target_solid_ref` (node id), `plane` (object with `point` and `normal`)

**Optional args:** `name`, `id`

**Returns:**
```json
{
  "file_id": "...",
  "id": "section-1",
  "op": "section",
  "target_solid_ref": "pad-1",
  "plane": { "point": [0,0,10], "normal": [0,0,1] }
}
```

---

## Plane definition

| `normal` | Slicing plane |
|---|---|
| `[0, 0, 1]` | XY-plane (horizontal slice) |
| `[0, 1, 0]` | XZ-plane |
| `[1, 0, 0]` | YZ-plane |
| Arbitrary `[nx, ny, nz]` | Oblique plane through `point` |

`plane.normal` does not need to be unit-length — the worker normalises it.

---

## Output

The section node produces a `TopoDS_Compound` of edges (not a solid).  The worker saves
it as a `.section` file kind.  From there it can be:
- Dimensioned and annotated (via `auto_dimension_generate`)
- Exported to DXF (via `auto_dimension_export_dxf`)
- Chained into a new `pad` to extrude the cross-section profile

---

## Usage snippets

```python
from kerf_cad_core.feature_section import build_section_node

node = build_section_node(
    "section-1",
    "pad-1",
    plane_point=[0.0, 0.0, 15.0],
    plane_normal=[0.0, 0.0, 1.0],
)
# node["op"] == "section"
# node["plane"] == {"point": [0,0,15], "normal": [0,0,1]}
```

```python
# LLM tool call — horizontal section 15 mm up a 30 mm pad
# {
#   "tool": "feature_section",
#   "file_id": "abc...",
#   "target_solid_ref": "pad-1",
#   "plane": { "point": [0, 0, 15], "normal": [0, 0, 1] }
# }
```

---

## Caveats

- Requires `BRepAlgoAPI_Section` in the OCCT WASM build (C1 probe at worker boot).  If
  absent the worker errors with a clear message; no fallback.
- Result is edges only — it is not a closed wire or face.  For dimensional drawing use
  `auto_dimension_generate` which accepts the section output.
- For iterative layered slicing at fixed Z-steps, use `feature_cam_layered` instead.
