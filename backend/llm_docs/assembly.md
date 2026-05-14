# Authoring `.assembly` files

An Assembly is a JSON file (`kind='assembly'`) that places **Components**
— instances of an Object from another file — at world transforms.

## Vocabulary (locked)

- **Part** — a whole `.jscad` (or `.feature` or `.step`) file. Returns an
  array of Objects. The Part is the FILE.
- **Object** — one entry in a Part's exported `[{id, geom}, ...]` array.
  Identified by its `id` ('base', 'peg', ...).
- **Component** — an Assembly's instance of a single Object placed at a
  4×4 transform. The Component lives inside the assembly file.

Never use "Part" for an Object or vice versa.

## File shape

```json
{
  "components": [
    {
      "id": "front-bracket-1",
      "file_id": "<uuid of the source file>",
      "object_id": "bracket",
      "transform": [
        1, 0, 0,  20,
        0, 1, 0,   0,
        0, 0, 1,   5,
        0, 0, 0,   1
      ],
      "params": {},
      "visible": true,
      "color": [0.8, 0.4, 0.2]
    }
  ]
}
```

Field rules:
- `components` is an array. Empty `[]` is a valid (empty) assembly.
- `id` — unique per assembly. Used for the Component label and as a
  reference target for the UI's selection / inspector.
- `file_id` — the source FILE's uuid (NOT a path). Get this from a
  `list_files` response — every file has its uuid alongside the path.
  If `list_files` doesn't surface uuids, use `read_file` on the source
  Part: the response includes the file's uuid in its envelope, OR walk
  `list_files` once to find the uuid by path.
- `object_id` — REQUIRED. Names a single Object id from the source
  Part's exported array. The legacy `'*'` wildcard is no longer
  accepted; place every Object as its own Component.
- `transform` — 16 floats, **row-major** 4×4 matrix.
  `[r00, r01, r02, tx, r10, r11, r12, ty, r20, r21, r22, tz, 0, 0, 0, 1]`
  Standard identity is `[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]`.
- `params` (optional) — free-form per-Component overrides the source
  Part's exported function reads.
- `visible` (optional) — default true.
- `color` (optional) — `[r, g, b]` 0..1, overrides the Object's color.

## Common edits via file ops

### Add a Component

1. `read_file('/parts.jscad')` — discover the Object ids.
2. `read_file('/main.assembly')` — get the existing JSON.
3. `edit_file('/main.assembly', '"components": [', '"components": [\n    {"id": "peg-1", "file_id": "<uuid>", "object_id": "peg", "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]},')`

For an empty assembly seed (`{"components": []}`), use `write_file` to
overwrite it cleanly:

```json
{
  "components": [
    {
      "id": "peg-1",
      "file_id": "<source-uuid>",
      "object_id": "peg",
      "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
    }
  ]
}
```

### Move a Component

Find the component object and overwrite the translation column. For
position only (no rotation), the matrix is:

```
[1, 0, 0, tx,
 0, 1, 0, ty,
 0, 0, 1, tz,
 0, 0, 0,  1]
```

So `edit_file` with the old transform array literal as `old_string` and
the new array literal as `new_string`.

### Compose translation + rotation + uniform scale

Three.js-compatible XYZ-Euler order: build R = Rz·Ry·Rx, then:

```
m = [
  R00·s, R01·s, R02·s, tx,
  R10·s, R11·s, R12·s, ty,
  R20·s, R21·s, R22·s, tz,
  0,     0,     0,     1
]
```

For example, 90° about Z, no scale, position (10, 0, 0):

```
[ 0, -1, 0, 10,
  1,  0, 0,  0,
  0,  0, 1,  0,
  0,  0, 0,  1]
```

### Remove a Component

`edit_file` with the full Component object (including the trailing
comma if not the last entry) as `old_string` and `""` as `new_string`.

### Cycle safety

Don't reference an assembly from inside itself or any of its descendant
assemblies. The frontend rejects the load on a cycle; it's also
unfixable via the chat path once written, so always verify the
`file_id` you cite isn't (transitively) the assembly you're editing.

## Insert dialog rationale

The frontend's "Insert" dialog asks the user to pick an Object id — the
LLM should follow the same flow: read the source Part, list its
Object ids, then add one Component per Object id you intend to place.
Don't try to "broadcast" to all Objects in a Part; the model is
explicit at the Component level.
