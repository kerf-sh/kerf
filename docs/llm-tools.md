# LLM tools

The catalog of tools chat can call. Each tool is a Python function in
`backend/tools/`; the agent loop dispatches to it via asyncio and
streams results back to the model.

The surface is intentionally **small and stable**. Domain-specific edit
tools (formerly `assembly_*`, `drawing_*`, `feature_*`, `set_part_*`,
`add_component`, …) were removed in favour of a doc-search-first model:
the LLM consults an embedded authoring corpus (`search_kerf_docs`) and
then edits the file's JSON directly via the standard file ops. This
keeps the tool count stable as new domains land — the new behaviour is
authored as a doc, not a tool.

## Permissions

Every tool is either **read** (viewer+) or **write** (editor+). Viewers
calling write tools get `{"error":"...", "code":"FORBIDDEN"}` — never a 500.
Tool-level errors always come back as JSON the model can reason about.

## Files

| Tool             | Role    | What it does                                            |
|------------------|---------|---------------------------------------------------------|
| `list_files`     | viewer+ | Flat list of every file's absolute path + kind + size   |
| `read_file`      | viewer+ | Read text content. Paths under `/docs/llm/` route to the embedded authoring corpus instead of the project tree. |
| `write_file`     | editor+ | Overwrite a file's content; auto-creates folders        |
| `edit_file`      | editor+ | Replace one unique substring; errors if 0 or >1 matches |
| `create_file`    | editor+ | Make a new `file` / `folder` / `assembly` / `drawing`   |
| `delete_file`    | editor+ | Soft-delete a file or folder (recursive)                |
| `search_code`    | viewer+ | Case-insensitive substring search across text files     |
| `import_step`    | editor+ | Download a STEP file from an HTTPS URL into the project. 30s timeout, 50 MB cap. |

Path conventions: POSIX-like, leading `/`, no trailing `/`. Root is `/`.

## Object operations

For mutating Objects inside a JSCAD Part (the `[{id, geom}, …]` return
literal). Both rely on bracket-matching — they bail with `PARSE_FAILED`
on non-conventional layouts.

| Tool                | Role    | What it does                                          |
|---------------------|---------|-------------------------------------------------------|
| `duplicate_object`  | editor+ | Clone one Object entry; default new id `<id>-copy`    |
| `delete_object`     | editor+ | Remove one Object entry from the array                |

## Validation + queries

| Tool             | Role    | What it does                                                |
|------------------|---------|-------------------------------------------------------------|
| `validate_jscad` | viewer+ | Stub — real validation runs in the browser                  |
| `generate_bom`   | viewer+ | Walks every assembly + part, rolls up Component instances by MPN, returns rows + total |

## Scaffolding (canonical seeds)

These produce a properly-shaped JSON / TSX seed the LLM would otherwise
have to guess (version field, default content, validators). After
scaffolding, the LLM edits the file via the standard write/edit tools.

| Tool             | Role    | What it does                                                |
|------------------|---------|-------------------------------------------------------------|
| `create_sketch`  | editor+ | New `.sketch` with version=1, plane, origin point.          |
| `create_feature` | editor+ | New `.feature` with empty `features[]` and version=1.       |
| `create_part`    | editor+ | New `.part` with required name + sane defaults.             |
| `create_circuit` | editor+ | New `.circuit.tsx` with a tscircuit `<board>` template.     |

## Authoring corpus

| Tool                | Role    | What it does                                                |
|---------------------|---------|-------------------------------------------------------------|
| `search_kerf_docs`  | viewer+ | Keyword-searches an embedded markdown corpus that documents every non-`.jscad` file kind. Returns `{path, title, excerpt, score}` hits. |

The hits' `path` values are `/docs/llm/<topic>.md`. The LLM follows up
with `read_file('/docs/llm/<topic>.md')` (the read_file tool routes
`/docs/llm/` paths to the embedded corpus instead of the project tree).

Pages currently in the corpus:

- `assembly.md` — Component placement; transform shape; cycle rules.
- `sketch.md` — Entity types + the planegcs constraint vocabulary.
- `feature.md` — OCCT timeline operations: pad / pocket / revolve /
  fillet / chamfer / shell / hole. Notes on future Rhino-style ops.
- `drawing.md` — Multi-sheet shape, dimensions, annotations,
  centerlines, breaks, GD&T.
- `part.md` — Library metadata: distributors, photos, visibility.
- `circuit.md` — tscircuit JSX patterns and selectors.
- `jscad.md` — JSCAD authoring conventions.
- `index.md` — table of contents with one-line per page.

The corpus is loaded at startup via `importlib.resources`
(see `backend/tools/docs.py`). Adding or updating an authoring
guide is a markdown edit + server restart — no schema changes, no migration.

## Revisions

| Tool                | Role    | What it does                                          |
|---------------------|---------|-------------------------------------------------------|
| `list_revisions`    | viewer+ | Per-file edit history, newest first, with previews    |
| `restore_revision`  | editor+ | Roll a file back; clears `deleted_at` if soft-deleted |

## When chat reaches for which tool

- *"Make this 6 mm thick"* (with a chip referencing an Object) →
  `read_file`, then `edit_file` with a tight substring pair.
- *"Add a fillet to the top edge"* of a `.feature` →
  `search_kerf_docs("fillet feature")` → `read_file('/docs/llm/feature.md')`
  → `read_file` the .feature → `edit_file` to append a fillet node.
- *"Insert two of bracket.jscad's wall Object"* in an assembly →
  `search_kerf_docs("assembly add component")` →
  `read_file('/docs/llm/assembly.md')` → `read_file` the bracket file
  to discover Object ids → `edit_file` the assembly's `components`
  array.
- *"Create a 3-view drawing of the assembly"* → `create_file` with
  `kind='drawing'` and an empty `{}` content (the frontend hydrates
  defaults), or `search_kerf_docs("drawing standard views")` → seed
  with a pre-shaped `sheets[].views[]` array via `write_file`.
- *"What did this file look like an hour ago?"* → `list_revisions`,
  then `restore_revision` if the user confirms.

## Where the source lives

- Tool registry — `backend/tools/registry.py`
- Implementations — per-domain files in `backend/tools/` (`file_ops.py`,
  `object_ops.py`, `scaffold.py`, `revisions.py`, `validation.py`, etc.)
- Authoring corpus — `backend/llm_docs/*.md` (loaded via
  `importlib.resources` at startup)
- Wire schema for tool calls / results — see `backend/llm_docs/` (per-kind specs) and `docs/v1-rpc.md`

Adding a new tool is a one-file change: write the spec, write the
executor, add an entry to `Registry` in `registry.py`. Adding a new
authoring page is a single `.md` edit + server restart.

Next: [getting-started.md](./getting-started.md)
