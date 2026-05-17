# feature_cut_from_sketch — Face-Oriented Sketch Cut

Append a `cut_from_sketch` node to a `.feature` file.  Subtracts a sketched region from
a specific planar face of a target body by extruding the cutter normal to **that face**
rather than normal to the sketch plane.

OCCT path: `faceById` → `faceFrame` → `placeFaceOnPlane` → `BRepPrimAPI_MakePrism`
(cutter) → `BRepAlgoAPI_Cut_3`.

---

## When to use

Keywords: cut from sketch, cut on face, face cut, inclined face cut, side face pocket,
cut slot on face, face-oriented cut, cut_from_sketch, sketch on face, cut on inclined
surface, cut on angled face.

---

## Entrypoints

### `validate_cut_from_sketch_args(target_face_id, sketch_path, depth, reverse) -> tuple[str|None, str|None]`

Pure validation.  Returns `(error_msg, error_code)` or `(None, None)`.

---

### `build_cut_from_sketch_node(node_id, target_id, target_face_id, sketch_path, depth, reverse, name, target_face_name) -> dict`

Build the feature-node dict with dual face reference (persistent name + legacy integer fallback):

```json
{
  "id": "cut-1",
  "op": "cut_from_sketch",
  "target_id": "pad-1",
  "target_face_name": "Pad-A.TopCap",
  "target_face_id": 5,
  "sketch_path": "/slot-profile.sketch",
  "depth": 8.0,
  "reverse": false
}
```

---

## LLM tool

**Name:** `feature_cut_from_sketch`

**Required args:** `file_id` (UUID), `target_id` (node id), `sketch_path`, `depth` (> 0 mm)

At least one face reference is required: `target_face_name` and/or `target_face_id`.

**Optional args:**
- `target_face_name` — persistent face name from the worker's `faceNames` map (e.g. `"Pad-A.TopCap"`)
- `target_face_id` — integer face index (fallback when `target_face_name` absent/stale)
- `reverse` — `false` (default: cut along −normal) | `true` (cut along +normal)
- `name`, `id`

**Returns:**
```json
{
  "file_id": "...",
  "id": "cut-1",
  "op": "cut_from_sketch"
}
```

---

## Difference from `pocket`

| | `pocket` | `cut_from_sketch` |
|---|---|---|
| Cutter axis | Normal to **sketch plane** | Normal to **target face** |
| Use case | Flat-face pocket | Pocket on inclined / side face |
| Face re-creation needed? | No | No |
| Face reference required | No | Yes |

---

## Face reference best practices

1. **Always supply `target_face_name`** (persistent name from Phase 4 face-naming).
   This survives upstream topology changes.
2. Also supply `target_face_id` as integer fallback for backward compatibility.
3. If the upstream pad profile changes shape after this node is written, re-pick the face
   and update `target_face_name` — the integer index may shift.

---

## Usage snippets

```python
from kerf_cad_core.feature_cut_from_sketch import build_cut_from_sketch_node

node = build_cut_from_sketch_node(
    "cut-1", "pad-1", 5,            # node_id, target_id, target_face_id
    "/slot.sketch", 8.0, False,     # sketch_path, depth, reverse
    name="Side slot",
    target_face_name="Pad-A.RightFace",
)
```

```python
# LLM tool call
# {
#   "tool": "feature_cut_from_sketch",
#   "file_id": "abc...",
#   "target_id": "pad-1",
#   "target_face_name": "Pad-A.TopCap",
#   "target_face_id": 5,
#   "sketch_path": "/notch.sketch",
#   "depth": 5.0
# }
```

---

## Caveats

- `reverse=true` is needed when the face normal points away from the body interior (e.g.
  a bottom face whose outward normal points downward, away from the material).
- No through-cut support: `depth` must be < face-normal thickness of the body at that
  face.  Exceeding the wall thickness produces an open shell.
- `target_face_id` is the post-evaluation face index from the worker's enumeration pass
  (same convention as `push_pull`).
