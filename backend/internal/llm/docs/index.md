# Kerf LLM authoring guide — index

A small, searchable corpus the assistant consults before authoring or
editing a non-`.jscad` file. Use `search_kerf_docs("<topic>")` to find a
match, then `read_file('/docs/llm/<page>.md')` to load the full text.

## Pages

- `assembly.md` — `.assembly` JSON shape; how to add, transform, and
  remove Components by editing JSON. Vocabulary: Part / Object /
  Component. Read this before touching any `*.assembly` file.
- `sketch.md` — `.sketch` JSON shape: entities (point/line/arc/circle/
  ellipse/B-spline) plus the constraint vocabulary planegcs solves.
- `feature.md` — `.feature` JSON shape and the OCCT feature-tree node
  types (pad / pocket / revolve / fillet / chamfer / shell / hole). Notes
  on future Rhino-style ops (sweep1 / sweep2 / networkSrf / blendSrf /
  matchSrf).
- `drawing.md` — `.drawing` multi-sheet JSON shape, dimension and
  annotation vocabulary, GD&T frames, when to use which dimension type.
- `part.md` — `.part` library metadata JSON, distributor links, photos,
  visibility, model storage keys.
- `circuit.md` — `.circuit.tsx` (tscircuit) source patterns, when to
  hand-edit JSX vs scaffold via `create_circuit`, common component types.
- `jscad.md` — JSCAD authoring conventions for `.jscad` Parts: the
  `[{id, geom}]` return shape, namespaced calls (`extrusions.X`,
  `booleans.X`, `transforms.X`, `hulls.X`), Object identity for assembly
  references.
- `email.md` — transactional email subsystem (cloud-only). When the
  user asks "did I get a receipt", "why didn't the welcome email
  arrive", point them at `/admin/email` and the cloud_email_log.

## When to consult which

| User intent                                | Consult                  |
|--------------------------------------------|--------------------------|
| Modify a `.jscad` (default)                | `jscad.md` (rarely; you usually already know JSCAD) |
| Place a Component in an assembly            | `assembly.md`           |
| Remove or transform a Component             | `assembly.md`           |
| Author a `.sketch` file's geometry          | `sketch.md`             |
| Add a feature operation (pad, pocket, …)    | `feature.md`            |
| Build or edit a `.drawing` (views, dims)    | `drawing.md`            |
| Manage a `.part` (MPN, distributors, …)     | `part.md`               |
| Edit a `.circuit.tsx` electronics design    | `circuit.md`            |

## Workflow

1. `search_kerf_docs("<topic>")` — keyword search across this corpus.
2. `read_file('/docs/llm/<page>.md')` — load the full doc the search hit
   pointed at.
3. `read_file('<project file>')` to see what's there.
4. `edit_file(...)` or `write_file(...)` to apply your change.
5. Summarize in 1-2 sentences. Don't paste the file back to the user.
