# `feature_mirror` — mirror a feature or body about a plane

Appends a `mirror_feature` node to a `.feature` file. The node mirrors
either a named feature node or an entire body about a world coordinate
plane (`XY`, `XZ`, `YZ`) or a planar face. When `merge=true` (the
default) the mirrored copy is boolean-unioned with the original to
produce a single symmetric solid.

## Schema

```json
{
  "id": "mirror_feature-1",
  "op": "mirror_feature",
  "params": {
    "source_feature_id": "pad-1",
    "mirror_plane": "XZ",
    "merge": true
  }
}
```

### Parameters

| Parameter          | Type           | Required        | Default | Notes                                                       |
|--------------------|----------------|-----------------|---------|-------------------------------------------------------------|
| `file_id`          | string (uuid)  | yes             | —       | Target `.feature` file id                                   |
| `source_feature_id`| string         | one of these two| —       | Id of the feature node to mirror                            |
| `source_body_id`   | string         | one of these two| —       | Id of the entire body to mirror                             |
| `mirror_plane`     | `"XY"` \| `"XZ"` \| `"YZ"` | one of these two | — | World plane to mirror across              |
| `mirror_face_id`   | integer        | one of these two| —       | Post-eval face index to use as the mirror plane             |
| `merge`            | boolean        | no              | `true`  | Union the mirror with the original when true                |
| `name`             | string         | no              | `""`    | Human-readable label for the node                           |

**Mutual exclusion rules**:
- Exactly one of `source_feature_id` / `source_body_id` must be supplied.
- Exactly one of `mirror_plane` / `mirror_face_id` must be supplied.

## Examples

### Mirror left arm to right

A robotic arm body has been modelled on the left side of the XZ plane.
Mirror it about XZ to produce a symmetric right-side copy and union both:

```text
feature_mirror(
  file_id           = <arm.feature id>,
  source_body_id    = "arm_body",
  mirror_plane      = "XZ",
  merge             = true,
  name              = "right_arm_mirror"
)
```

Resulting node:

```json
{
  "id": "mirror_feature-1",
  "op": "mirror_feature",
  "name": "right_arm_mirror",
  "params": {
    "source_body_id": "arm_body",
    "mirror_plane": "XZ",
    "merge": true
  }
}
```

### Mirror a pad feature about a face

A bracket has a mounting boss on one side (modelled as `pad-2`). Mirror
it across the flat back face (face 9) to place an identical boss on the
opposite side, without merging (keep as separate solid):

```text
feature_mirror(
  file_id            = <bracket.feature id>,
  source_feature_id  = "pad-2",
  mirror_face_id     = 9,
  merge              = false,
  name               = "opposite_boss"
)
```

```json
{
  "id": "mirror_feature-1",
  "op": "mirror_feature",
  "name": "opposite_boss",
  "params": {
    "source_feature_id": "pad-2",
    "mirror_face_id": 9,
    "merge": false
  }
}
```

## Validation rules

- Exactly one of `source_feature_id` / `source_body_id` must be non-empty.
- Exactly one of `mirror_plane` / `mirror_face_id` must be provided.
- `mirror_plane` must be `"XY"`, `"XZ"`, or `"YZ"` (case-insensitive).
- `file_id` must be a valid UUID pointing to a `feature`-kind file.
- `merge` defaults to `true` when omitted.
