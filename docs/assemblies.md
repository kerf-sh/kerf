# Assemblies

Compose Parts and Objects into a single placed scene.

## Vocabulary refresher

If these aren't immediate, read [concepts.md](./concepts.md) first.

- **Part** — a `.jscad` file. Default-exports a function that returns an array.
- **Object** — one entry of that array. `{ id, geom }`. Click-handles in the viewport.
- **Component** — an Assembly's instance of one Object placed at a 4×4 transform.

## Create an assembly

In the file tree: **New file → Assembly**. An empty `.assembly` opens in the
Assembly Editor.

<!-- screenshot: empty assembly with insert button highlighted -->

The Editor shows:

- Left: the Components list — one row per placed Component, with its source
  Part / Object and current transform.
- Center: a 3D viewport rendering the composed scene.
- Right: a transform panel for the selected Component (position, rotation,
  scale, parent).

## Insert dialog

Click **Add component**. A picker appears listing every other file in the
project. Pick a Part:

- **Single-Object Part** → added directly with identity transform.
- **Multi-Object Part** → a modal opens listing every Object with checkboxes
  (all checked by default), plus a **Place as rigid group** toggle.

Confirming the modal creates one Component per checked Object. With the rigid
group toggle on, every Component starts at the same transform — useful when
you want to move a multi-Object Part as a unit. With it off, each Component
gets the identity and you can scatter them individually.

This mirrors OnShape's "Insert" UX, by design.

## Transforms

A Component's transform is a row-major 4×4 matrix (Three.js convention). The
right-hand panel decomposes it into:

- Position `(x, y, z)` in mm
- Rotation `(rx, ry, rz)` in degrees, XYZ Euler order
- Uniform scale (or per-axis if you need it)

Editing any field triggers a re-render. Drag handles in the viewport for
direct manipulation are on the roadmap.

## Rigid groups

A "rigid group" in Kerf is a soft convention: multiple Components sharing the
same transform expression behave as a unit when you edit that one transform.
There's no formal grouping primitive yet — moving the group means selecting
all members and applying the same delta. The Insert dialog's rigid-group
toggle just sets up that initial shared transform for you.

## Editing the source Part from an Assembly

Selecting a Component highlights its source Part in the file tree. Open the
`.jscad` file, edit it, and the Assembly viewport re-renders the next time the
JSCAD evaluation completes (worker, debounced).

## ObjectsPanel: duplicate / delete an Object

Inside a `.jscad` file, the Objects panel lists every Object. Each row has:

- **Duplicate** — clones the Object entry inline in the source code, giving
  the clone an `<id>-copy` id.
- **Delete** — removes the Object entry entirely.

Both go through the standard PATCH-with-revision path so they undo cleanly
(Cmd+Z) and show up in History. The bracket-matching helper bails with a
toast if your file isn't a clean `return [{id, geom}, …]` — wrap any
generation logic in a function that returns the array literal at the top
level.

The same operations are exposed to chat as `duplicate_object` and
`delete_object` tools.

## Assemblies referencing assemblies

Currently a Component must reference an `.jscad` Object. Nested assemblies
(an Assembly that places another Assembly as a sub-tree) aren't supported
yet — flatten the inner Assembly into Components in the outer one.

## STEP-backed Components

A `.step` file in the project shows up in the Insert picker like any other
Part. The renderer triangulates the STEP server-side (planned — today it's
client-side via `occt-import-js`) and treats each top-level body as an Object
you can place.

## Wire format

An Assembly's `content` is JSON:

```ts
type Assembly = {
  components: Array<{
    id: string                     // unique within this assembly
    file_id: string                // the source Part file
    object_id: string              // an Object id from that Part
    transform: number[16]          // row-major 4x4
    params?: Record<string, any>   // optional Part-function params
    visible?: boolean              // default true
    color?: [number, number, number]   // optional 0–1 rgb override
  }>
}
```

Legacy assemblies that used `object_id: '*'` (place every Object) load via a
back-compat shim and are migrated to one Component per Object on next save.

## LLM tools

Chat can mutate assemblies via these tools (all editor+):

- `assembly_add` — place a new Component (`source_path`, `object_id`,
  position/rotation/scale).
- `assembly_set_transform` — update an existing Component's pose.
- `assembly_set_object` — change which Object a Component references.
- `assembly_remove_component` — delete a Component.
- `duplicate_object` / `delete_object` — mutate the source Part itself.

A `*` wildcard is no longer accepted for `object_id` on writes — the LLM
issues one `assembly_add` per Object, matching the human Insert flow.

Next: [drawings.md](./drawings.md)
