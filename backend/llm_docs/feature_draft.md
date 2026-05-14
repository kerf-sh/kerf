# `feature_draft` — taper faces for mold release

Appends a `draft` node to a `.feature` file. Draft tilts a set of faces
by `angle_deg` relative to a neutral (parting-line) plane — the standard
operation for injection-molded parts so the part releases cleanly from the
mold.

## Schema

```json
{
  "id": "draft-1",
  "op": "draft",
  "params": {
    "face_ids": [3, 4, 5],
    "neutral_plane_face_id": 2,
    "angle_deg": 2.0,
    "pull_direction": "outward"
  }
}
```

### Parameters

| Parameter               | Type             | Required | Default    | Notes                                        |
|-------------------------|------------------|----------|------------|----------------------------------------------|
| `file_id`               | string (uuid)    | yes      | —          | Target `.feature` file id                    |
| `face_ids`              | array of integer | yes      | —          | Post-eval face indices to taper (≥1)         |
| `neutral_plane_face_id` | integer          | yes      | —          | Face id of the neutral / parting-line plane  |
| `angle_deg`             | number           | yes      | —          | Taper angle in degrees; must be in [-30, 30] |
| `pull_direction`        | `"outward"` \| `"inward"` | no | `"outward"` | Direction of taper relative to neutral plane |
| `name`                  | string           | no       | `""`       | Human-readable label for the node            |

**Face id stability** — face indices are assigned in TopExp explorer order
on each OCCT evaluation. They are stable for pure parameter edits but will
shuffle when features are added, removed, or reordered upstream. See
`feature.md` "Edge / face id stability".

## Examples

### Housing wall taper

A rectangular housing body (from `pad-1`) needs 2° outward draft on its
four side walls (faces 3, 4, 5, 6) relative to the parting plane at the
top face (face 2):

```text
feature_draft(
  file_id               = <housing.feature id>,
  face_ids              = [3, 4, 5, 6],
  neutral_plane_face_id = 2,
  angle_deg             = 2.0,
  pull_direction        = "outward",
  name                  = "side_wall_draft"
)
```

The resulting node in the feature tree:

```json
{
  "id": "draft-1",
  "op": "draft",
  "name": "side_wall_draft",
  "params": {
    "face_ids": [3, 4, 5, 6],
    "neutral_plane_face_id": 2,
    "angle_deg": 2.0,
    "pull_direction": "outward"
  }
}
```

### Lens taper (inward)

An optical lens body requires a slight inward taper on the curved side
face (face 7) to seat tightly against the lens barrel. Neutral plane is
the flat back face (face 1):

```text
feature_draft(
  file_id               = <lens.feature id>,
  face_ids              = [7],
  neutral_plane_face_id = 1,
  angle_deg             = 1.5,
  pull_direction        = "inward",
  name                  = "barrel_seat_taper"
)
```

```json
{
  "id": "draft-1",
  "op": "draft",
  "name": "barrel_seat_taper",
  "params": {
    "face_ids": [7],
    "neutral_plane_face_id": 1,
    "angle_deg": 1.5,
    "pull_direction": "inward"
  }
}
```

## Validation rules

- `face_ids` must be a non-empty array.
- `neutral_plane_face_id` must be present.
- `angle_deg` must be a number in the closed interval [-30, 30].
- `pull_direction` must be exactly `"inward"` or `"outward"`.
- `file_id` must be a valid UUID pointing to a `feature`-kind file.
