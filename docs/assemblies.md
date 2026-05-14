# Assemblies

Compose multiple Parts into a single placed scene, define mating relationships between components, and manage bill-of-materials rollup across configurations.

## Core concepts

Read [concepts.md](./concepts.md) for the foundational vocabulary:

- **Part** — a `.jscad` file that default-exports a function returning an array of Objects
- **Object** — one `{ id, geom }` entry from a Part, with click-handles in the viewport
- **Component** — an Assembly's instance of one Object, placed at a 4×4 transform
- **Mate** — a constraint between two Components (coincident, distance, angle, etc.)

## The .assembly JSON format

```json
{
  "schema": "kerf.assembly.v1",
  "config_id": "default",
  "components": [
    {
      "id": "bracket_1",
      "file_id": "part-uuid-bracket",
      "object_id": "body",
      "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,10,1],
      "params": {},
      "visible": true,
      "color": [0.8, 0.2, 0.2]
    }
  ],
  "mates": [
    {
      "id": "mate_1",
      "type": "coincident",
      "entityA": { "component": "bracket_1", "face": 0 },
      "entityB": { "component": "base_1", "face": 2 }
    }
  ]
}
```

### Field reference

| Field         | Type       | Description                                       |
|---------------|------------|---------------------------------------------------|
| `config_id`   | string     | Identifies the configuration variant in use        |
| `components`  | array      | All placed Components in this Assembly            |
| `mates`       | array      | All mate constraints between Components           |

## Components

Each component entry specifies:

```json
{
  "id": "bolt_1",
  "file_id": "part-uuid-hex-bolt",
  "object_id": "hex-head",
  "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 10,5,20,1],
  "params": { "thread_pitch": 1.5 },
  "visible": true,
  "color": [0.5, 0.5, 0.5]
}
```

- `id` — unique string within this Assembly
- `file_id` — UUID of the source Part `.jscad` file
- `object_id` — which Object from that Part to instantiate
- `transform` — row-major 4×4 matrix (Three.js convention): position in elements [12,13,14], rotation/scale in the 3×3 upper-left
- `params` — optional runtime parameters passed to the Part's export function
- `visible` — render toggle (default `true`)
- `color` — optional RGB override in 0–1 range

## Transforms

The 4×4 row-major matrix follows Three.js conventions:

```
[ r00, r01, r02, tx,
  r10, r11, r12, ty,
  r20, r21, r22, tz,
  0,   0,   0,   1  ]
```

The right panel decomposes this into:

- **Position** `(x, y, z)` — translation in mm
- **Rotation** `(rx, ry, rz)` — XYZ Euler angles in degrees
- **Scale** — uniform scalar (per-axis scale lives in the matrix's 3×3)

Editing any field in the panel triggers an immediate re-render.

## Mates

The `mates` array defines geometric relationships between Components. Each mate type constrains degrees of freedom between a pair of component faces or features:

### Mate types

| Mate          | DOFs constrained              | Parameters                    |
|---------------|-------------------------------|-------------------------------|
| `coincident`  | 3 (translation) + 2 (rotation) | —                             |
| `concentric`  | 3 (translation)               | —                             |
| `parallel`    | 2 (rotation)                  | —                             |
| `perpendicular`| 1 (rotation)                 | —                             |
| `distance`    | 3 (translation)               | `value` (mm)                  |
| `angle`       | 2 (rotation)                  | `value` (degrees)             |
| `tangent`     | 2 (translation) + 1 (rotation)| `inside` (bool)               |

```json
{
  "id": "slot_mate",
  "type": "distance",
  "entityA": { "component": "pin_1", "face": 1 },
  "entityB": { "component": "slot_1", "face": 0 },
  "value": 2
}
```

### Mate entity reference

Each `entityA` / `entityB` in a mate references:

```json
{ "component": "bolt_1", "face": 0 }
```

Face indices refer to the ordered face list of the component's underlying geometry.

## Solver behavior

The Assembly solver resolves all transforms such that every mate constraint is satisfied simultaneously. The solver:

1. Builds a graph of Components and Mates
2. Identifies rigid groups (subgraphs fully constrained by mates)
3. Solves for remaining DOFs using the positional and rotational constraints
4. Reports conflicts — two mates that cannot be satisfied together

If the solver cannot converge, it reports the conflicting mates and leaves transforms unchanged.

## Rigid groups

When a set of Components is fully constrained by mates, they move together as a rigid group. Dragging one moves all members that share its mate chain.

## Cross-project parts with `assembly_add_external_component`

Reference a Part from another project in the current Assembly:

```json
{
  "tool": "assembly_add_external_component",
  "source_project_id": "project-uuid-other",
  "source_file_id": "part-uuid-external",
  "object_id": "body",
  "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,50,1],
  "placed_id": "imported_bracket"
}
```

External components are read-only in the current project. If the source project updates, the Assembly picks up the new geometry on next reload.

## BOM rollup

The Bill of Materials aggregates all Components across configurations:

```json
{
  "config_id": "default",
  "bom": [
    {
      "part_id": "part-uuid-hex-bolt",
      "part_name": "hex-bolt.jscad",
      "objects": ["hex-head", "thread"],
      "quantity": 4,
      "config_variants": { "M6x20": 2, "M6x35": 2 }
    }
  ]
}
```

- `quantity` — total count across all configurations
- `config_variants` — per `config_id` breakdown when multiple configurations exist

## Configuration pinning with `config_id`

The `config_id` field pins the Assembly to a specific named configuration. When a Part is instantiated with `params`, those params define the configuration variant. Swapping `config_id` loads a different variant set:

```json
{
  "config_id": "rev-b",
  "components": [
    {
      "id": "base_1",
      "file_id": "part-uuid-base",
      "object_id": "body",
      "params": { "variant": "rev-b", "length": 150 }
    }
  ]
}
```

Parts that do not define variants for a given `config_id` use their default parameters.

## LLM tools

| Tool                         | Purpose                                      |
|------------------------------|----------------------------------------------|
| `assembly_add`               | Place a new Component                        |
| `assembly_add_external_component` | Reference a Part from another project |
| `assembly_set_transform`     | Update a Component's position/rotation/scale |
| `assembly_set_object`        | Change which Object a Component references   |
| `assembly_remove_component`  | Delete a Component                           |
| `assembly_add_mate`          | Add a mate constraint between two Components |
| `assembly_remove_mate`       | Delete a mate                                |
| `assembly_set_config`        | Change the active `config_id`                |
| `duplicate_object`           | Clone an Object inside its source Part       |
| `delete_object`              | Remove an Object from its source Part        |

## Related

- [Sketching](./sketching.md) — 2D profiles that become 3D Parts
- [Parts & Objects](./concepts.md) — the JSCAD file model
- [Drawings](./drawings.md) — 2D drawing output from assemblies