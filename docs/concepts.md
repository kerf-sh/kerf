# Concepts

Kerf's mental model in five nouns: Project, File, Part, Object, Component.

## The hierarchy

```
Project
└── File           (.jscad, .sketch, .assembly, .drawing, .step, ...)
    └── Object     (one entry of the array a .jscad file exports)
                   └── Component  (an Assembly's instance of an Object)
```

Everything else (chat threads, revisions, members, share links) hangs off the
Project.

## Project

A workspace owned by a user, optionally shared with members or via share links.
A Project has a tree of Files, a chat history, and a visibility setting
(`private` / `unlisted` / `public`). On creation, a default `main.jscad` file
is seeded.

Projects are isolated — files cannot import across project boundaries.

## File

The unit of editing. Every File has a `kind`:

| Kind        | Extension     | What it stores                                       |
|-------------|---------------|------------------------------------------------------|
| `file`      | `.jscad`      | JSCAD source: a Part — see below                     |
| `folder`    | n/a           | Just a parent for organization                       |
| `assembly`  | `.assembly`   | JSON: list of Components referencing other Parts     |
| `drawing`   | `.drawing`    | JSON: multi-sheet 2D technical drawing               |
| `sketch`    | `.sketch`     | JSON: planegcs 2D constraint sketch                  |
| `step`      | `.step` etc.  | Binary STEP geometry, served from object storage     |

Text files keep their content in Postgres directly. Binary files (today: STEP)
keep a pointer; the bytes live in the configured Storage backend (local disk,
S3/R2/MinIO, or filesystem-mirrored). See `docs/architecture.md` for the wire shapes.

Every text edit appends a row to `file_revisions`, capped at 200 per file. The
File History drawer (and Cmd+Z) reads from there. Deletes are soft — the row
gets a `deleted_at` and stays restorable.

## Part vs. Object

These two are the most-confused pair, so they get their own section.

- A **Part** is an entire `.jscad` file. It exports a default function that
  returns an array.
- An **Object** is one entry of that array — `{ id, geom }` where `geom` is a
  `@jscad/modeling` Geom3 and `id` is the handle used everywhere else (clicked
  in the viewport, dropped as a chip in chat, referenced from assemblies).

```js
// bracket.jscad — a Part.
export default function () {
  const wall = primitives.cuboid({ size: [40, 4, 20] })
  const lip  = transforms.translate([0, 12, 0], primitives.cuboid({ size: [40, 4, 4] }))
  return [
    { id: 'wall', geom: wall },   // Object
    { id: 'lip',  geom: lip  },   // Object
  ]
}
```

A Part can contain one Object or many. JSCAD files in Kerf behave like
**OnShape "part studios"** — a single source file produces a family of related
solids, each independently selectable.

## Component

A Component lives inside an Assembly file. It references one Object from one
Part and places it at a 4×4 transform:

```ts
{ id: 'left-bracket', file_id: '...', object_id: 'wall', transform: [...16 nums] }
```

The Component `id` is unique within the Assembly and is what the renderer uses
as the clickable handle in the assembly viewport.

You can place the same Object multiple times (different `id`, different
transform) — that's how repeated parts (screws, clips, grommets) work.

## Sketch

A `.sketch` file is a 2D parametric profile: points, lines, arcs, circles, plus
geometric and dimensional constraints solved by `planegcs`. The output is a
Geom2 (closed loop) that a `.jscad` file imports:

```js
import profile from '/sketches/flange.sketch'
import { extrusions } from '@jscad/modeling'

export default function () {
  const body = extrusions.extrudeLinear({ height: 10 }, profile())
  return [{ id: 'flange', geom: body }]
}
```

Sketches are user-authored in the sketch editor; the LLM can `create_sketch`
but cannot mutate one beyond that. See [sketching.md](./sketching.md).

## Assembly

A `.assembly` file is an array of Components. The renderer composes them into
one scene; clicking selects a Component (not the underlying Object inside the
source Part). See [assemblies.md](./assemblies.md).

## Drawing

A `.drawing` file is one or more sheets, each with projected views from
`.jscad` / `.assembly` / `.step` sources, dimensions, annotations, and
engineering symbols. Coordinates are page millimetres. See
[drawings.md](./drawings.md).

## Two kernels, one project

Today, Kerf solves Geom3 by evaluating JSCAD code in a Web Worker
(triangulated mesh). On the roadmap is a `.feature` file kind backed by
OpenCASCADE, giving real B-rep features (precise fillets, lossless STEP
export, edge identity for selection-driven ops). Both kernels coexist in a
project on a per-file basis.

The full vocabulary is locked in `docs/architecture.md` + the per-kind specs under `backend/llm_docs/`. Anything that disagrees with
this doc is a bug — open an issue.

Next: [sketching.md](./sketching.md)
