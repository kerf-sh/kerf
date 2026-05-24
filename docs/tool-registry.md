# The AI workflow and tool system

Kerf's chat panel is an AI loop that can read, edit, and create any file in
your project through natural language. This page explains what happens when you
type a prompt, what tools are available, and how to extend the system.

---

## How a chat message becomes a model change

When you send a message in the Kerf chat panel:

1. Your message is appended to the thread; the server builds the LLM history.
2. The LLM receives the full tool registry, filtered to your role (viewers get
   read-only tools).
3. The LLM calls tools — `read_file`, `edit_file`, `search_kerf_docs`, etc.
4. Each tool result is streamed back into the chat as a result row.
5. Steps 2–4 repeat up to 10 times until the LLM has no more tool calls.
6. Any changed files are re-rendered and the viewport updates via SSE.

A single "make this 6 mm thick" request can chain
`search_kerf_docs → read_file → edit_file → validate_jscad` — all visible as
individual rows in the chat.

---

## OSS vs Cloud

The tool system is fully available in the OSS self-hosted build. Every one of
the ~150 tools across 19 plugins is present when you install the matching
persona.

On Kerf Cloud the same tools run on the hosted server; LLM tokens are metered
against your credits. On a self-hosted install you configure your own LLM API
key and no usage is metered.

---

## Core tools you use every day

These tools are always present regardless of persona:

| Kerf tool | What it does |
|-----------|--------------|
| `search_kerf_docs` | Full-text search across the embedded LLM docs corpus — always call this first for unfamiliar file kinds |
| `read_file` | Read any file in the project (or a corpus doc under `/docs/llm/`) |
| `write_file` | Overwrite a file's content |
| `edit_file` | Atomic find-and-replace inside a file — preferred over `write_file` for targeted edits |
| `create_file` | Create a new file or folder |
| `delete_file` | Soft-delete a file (revision history preserved) |
| `search_code` | Search text across all files in the project |
| `list_files` | List all files and folders in a project |
| `validate_jscad` | Check a JSCAD script for errors before save |

---

## The doc-search-first pattern

The ~150 tools are intentionally low-level (file read/write, feature node
append, BIM element mutation). Before touching an unfamiliar file kind, the AI
consults the authoring corpus:

```python
# What the AI does internally:
search_kerf_docs("fillet")                  # → [{path, title, excerpt, score}]
read_file("/docs/llm/feature.md")           # → authoring conventions for .feature files
# Then, armed with the right schema:
edit_file(path="part.feature", old="…", new="…")
```

Paths under `/docs/llm/` resolve to the in-memory corpus loaded at boot from
every plugin's `llm_docs/` folder — not the project tree. Adding support for a
new file kind means writing a corpus doc, not new tool functions.

---

## Tool categories by domain

Which tools are active depends on which persona is installed. Check live tools
at `GET /health/capabilities`.

| Kerf tool group | Plugin | Persona |
|-----------------|--------|---------|
| File ops, scaffold, revisions, equations | `kerf-api` | all |
| Doc search | `kerf-chat` | all |
| Sketch (create / edit constraint geometry) | `kerf-cad-core` | `mech`, `full` |
| Feature tree (pad, pocket, fillet, chamfer, shell, draft, holes) | `kerf-cad-core` | `mech`, `full` |
| Mesh, SubD, 3DM, curve ops | `kerf-imports` | `mech`, `full` |
| Drawings (hatches, leaders, dimensions) | `kerf-imports` | `mech`, `full` |
| Assembly + mates, tolerance stack | `kerf-mates` | `mech`, `full` |
| BIM elements, families, schedules, stairs, MEP, curtain walls | `kerf-bim` | `bim`, `full` |
| Electronics — schematic (ERC, buses, diff-pairs, hierarchy) | `kerf-electronics` | `electronics`, `full` |
| Electronics — PCB (routing, DRC, pours, net classes, via stitching) | `kerf-electronics` | `electronics`, `full` |
| FEA + simulation | `kerf-fem` | `mech`, `full` |
| CAM toolpaths | `kerf-cam` | `mech`, `full` |
| Topology optimisation | `kerf-topo` | `mech`, `full` |
| Render scene | `kerf-render` | `full` |
| Materials (cloud-hosted catalog) | `kerf-cloud` | cloud only |

---

## Access control: read vs write tools

Every tool is classified as **read** or **write**:

- **Read** (default): any project member including viewers.
- **Write**: requires `editor` role or higher. Viewers receive
  `{"error": "…", "code": "FORBIDDEN"}`.

Write tools are those whose names start with `set_`, `add_`, `create_`,
`delete_`, `run_`, `write_`, `edit_`, or that carry an explicit `write=True`
flag.

---

## Extending the AI: adding corpus docs

Drop a `.md` file in `packages/kerf-<name>/src/kerf_<name>/llm_docs/` and
restart the server. It will be picked up automatically and become searchable via
`search_kerf_docs`. File names become the corpus path (`/docs/llm/<filename>`).

This is the primary way to teach the AI about a new file format, workflow, or
convention — no new tool functions needed.

---

## Extending the AI: adding a tool

1. Pick the plugin that owns the domain.
2. Create `packages/kerf-<name>/src/kerf_<name>/tools/my_tool.py`.
3. Register it in the plugin's `register(app, ctx)`:

```python
from kerf_core.plugin import ToolSpec

ctx.tools.register(
    name="my_tool",
    spec=ToolSpec(
        name="my_tool",
        description="What this does.",
        parameters={"type": "object", "properties": {…}, "required": […]},
    ),
    handler=my_async_handler,
    write=True,   # omit for read-only tools
)
```

4. Write a test covering the happy path and at least one error path.
5. If the tool touches a new file kind, add a doc in `llm_docs/`.

---

## Tool error shape

Tools return a JSON-serialisable dict. Errors always use:

```json
{"error": "human-readable message", "code": "SNAKE_CASE_CODE"}
```

Common codes: `NOT_FOUND`, `BAD_ARGS`, `FORBIDDEN`, `TIMEOUT`. The LLM reads
`error` and `code` to decide how to recover — never throw Python exceptions
from a tool handler.

---

## See also

- [llm-tools.md](./llm-tools.md) — full per-tool reference
- [architecture.md](./architecture.md) — plugin system and boot sequence
- [contributing.md](./contributing.md) — plugin development guide
- [sdk.md](./sdk.md) — scripting Kerf from Python
