# 3D Assembly Mates

Mates are geometric constraints that define how components relate to each other in 3D space. They are used by the SolveSpace solver to compute the final positions of components in an assembly.

## Vocabulary

- **Mate**: A single geometric constraint between two component entities.
- **Entity**: A face, edge, vertex, or axis on a component.
- **Mate type**: The kind of geometric constraint (coincident, parallel, distance, etc.).

## Mate Types

| Type | Description | Value/Unit |
|------|-------------|------------|
| `coincident` | Two entities coincide at the same location | No |
| `concentric` | Two circular faces share the same axis and center | No |
| `parallel` | Two planar faces or axes are parallel | No |
| `perpendicular` | Two planar faces or axes are at 90° | No |
| `tangent` | A face and a curved surface touch tangentially | No |
| `distance` | Specified clearance between two entities | Yes (mm/cm/inch) |
| `angle` | Specified angle between two entities | Yes (deg/rad) |

## Entity Reference Shape

Each side of a mate (`a` and `b`) references a geometric entity:

```json
{
  "component_id": "front-bracket-1",
  "feature": "face",
  "feature_id": "f1"
}
```

`feature` must be one of: `face`, `edge`, `vertex`, `axis`
`feature_id` is the identifier of the specific feature on the component.

## File Shape

Mates live inside an `.assembly` file's `mates` array:

```json
{
  "components": [...],
  "mates": [
    {
      "id": "mate-1",
      "type": "coincident",
      "a": {
        "component_id": "bracket-left",
        "feature": "face",
        "feature_id": "f1"
      },
      "b": {
        "component_id": "plate-top",
        "feature": "face",
        "feature_id": "f3"
      }
    },
    {
      "id": "mate-2",
      "type": "distance",
      "a": {
        "component_id": "bracket-left",
        "feature": "face",
        "feature_id": "f1"
      },
      "b": {
        "component_id": "plate-top",
        "feature": "face",
        "feature_id": "f2"
      },
      "value": 5,
      "unit": "mm"
    }
  ]
}
```

## Using Mates Tools

### Add a mate

Use `add_mate` to append a constraint:

```
add_mate({
  assembly_file_id: "<uuid>",
  mate: {
    id: "my-mate",
    type: "coincident",
    a: { component_id: "comp-a", feature: "face", feature_id: "f1" },
    b: { component_id: "comp-b", feature: "face", feature_id: "f2" }
  }
})
```

For dimensional mates (distance/angle), include `value` and `unit`:

```
add_mate({
  assembly_file_id: "<uuid>",
  mate: {
    id: "gap-mate",
    type: "distance",
    a: { component_id: "part-1", feature: "face", feature_id: "f0" },
    b: { component_id: "part-2", feature: "face", feature_id: "f1" },
    value: 10,
    unit: "mm"
  }
})
```

### Delete a mate

```
delete_mate({ assembly_file_id: "<uuid>", mate_id: "my-mate" })
```

### List mates

```
list_mates({ assembly_file_id: "<uuid>" })
```

## Validation

- Every mate must have `type`, `a`, and `b` with valid component_id/feature/feature_id.
- Distance and angle mates require `value` and `unit`.
- All component_ids in mates must exist in the assembly.
- Duplicate mate ids are rejected.