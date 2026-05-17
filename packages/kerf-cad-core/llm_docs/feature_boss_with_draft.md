# feature_boss_with_draft — Pad + Draft Taper in One Step

Append a `boss_with_draft` node to a `.feature` file.  FreeCAD-parity shortcut: extrudes
a sketch profile AND applies a draft taper to all side faces in a single operation.

OCCT path: `BRepPrimAPI_MakePrism` → `walkSideFaces` → `BRepOffsetAPI_DraftAngle`.

---

## When to use

Keywords: boss with draft, draft angle, taper, extrude with taper, pad with draft, draft
taper, moulding boss, casting boss, draft extrusion, injection moulding boss, die cast
boss, BRepOffsetAPI_DraftAngle, neutral plane, feature draft.

---

## Entrypoints

### `validate_boss_with_draft_args(sketch_path, height, direction, draft_angle_deg, draft_direction) -> tuple[str|None, str|None]`

Pure validation.  Returns `(error_msg, error_code)` or `(None, None)`.

---

### `build_boss_with_draft_node(node_id, sketch_path, height, direction, draft_angle_deg, draft_direction, name) -> dict`

Build the feature-node dict:
```json
{
  "id": "boss_with_draft-1",
  "op": "boss_with_draft",
  "sketch_path": "/profile.sketch",
  "height": 20.0,
  "direction": "up",
  "draft_angle_deg": 3.0,
  "draft_direction": "outward"
}
```

---

## LLM tool

**Name:** `feature_boss_with_draft`

**Required args:** `file_id` (UUID), `sketch_path` (must end in `.sketch`), `height` (> 0 mm), `draft_angle_deg` (−30 to 30)

**Optional args:**
- `direction` — `"up"` (default) | `"down"` | `"symmetric"`
- `draft_direction` — `"outward"` (default) | `"inward"`
- `name`, `id`

**Returns:**
```json
{
  "file_id": "...",
  "id": "boss_with_draft-1",
  "op": "boss_with_draft"
}
```

When `draft_angle_deg == 0` the result is identical to a plain pad; a `hint` key is added
but the node is still valid.

---

## Parameter reference

| Parameter | Type | Range | Default | Notes |
|---|---|---|---|---|
| `sketch_path` | str | ends in `.sketch` | — | Closed-profile sketch |
| `height` | number | > 0 | — | Extrusion height in mm |
| `direction` | str | `up\|down\|symmetric` | `"up"` | Extrusion direction |
| `draft_angle_deg` | number | −30 to 30 | — | Taper angle in degrees |
| `draft_direction` | str | `outward\|inward` | `"outward"` | Side-face taper sense |

**`draft_angle_deg` sign convention** (with `draft_direction="outward"`):
- Positive → boss widens away from the sketch plane (wider at the base, narrower at the top)
- Negative → boss narrows away from the sketch plane

The neutral plane for the draft is always the sketch plane.

---

## Usage snippets

```python
from kerf_cad_core.feature_boss_with_draft import build_boss_with_draft_node

node = build_boss_with_draft_node(
    "boss-1", "/flange.sketch", 15.0, "up", 2.0, "outward"
)
# node["op"] == "boss_with_draft"
# node["draft_angle_deg"] == 2.0
```

```python
# LLM tool call — 20 mm boss with 3° outward taper for injection moulding
# {
#   "tool": "feature_boss_with_draft",
#   "file_id": "abc...",
#   "sketch_path": "/boss-profile.sketch",
#   "height": 20.0,
#   "draft_angle_deg": 3.0,
#   "draft_direction": "outward"
# }
```

---

## Caveats

- Eliminates the separate pad → face-picking → `feature_draft` workflow.
- Draft angle clamped to [−30°, 30°]; larger angles require a manual pad + separate
  `BRepOffsetAPI_DraftAngle` call outside this tool.
- `direction="symmetric"` centres the extrusion on the sketch plane (height/2 in each
  direction), then applies the full draft over the total height.
