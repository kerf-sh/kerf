# Tool registry

The LLM tool system is built around a shared `ToolRegistry` that every plugin
contributes to at boot. This document explains how the registry works, how to
add a tool, and how `search_kerf_docs` fits into the overall pattern.

## The registry contract

The registry is defined in `packages/kerf-chat/src/kerf_chat/tools/registry.py`:

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict   # JSON Schema for the tool's parameters

@dataclass
class Tool:
    spec: ToolSpec
    write: bool = False  # True → requires editor role; False → viewer-readable
    run: Callable = None

Registry: list[Tool] = []
```

Plugins register by decorating a handler function:

```python
from kerf_chat.tools.registry import register, ToolSpec

@register(ToolSpec(
    name="feature_fillet",
    description="Add a rolling-ball fillet to specified B-rep edges.",
    input_schema={
        "type": "object",
        "properties": {
            "part_path": {"type": "string"},
            "edge_ids":  {"type": "array", "items": {"type": "string"}},
            "radius":    {"type": "number"},
        },
        "required": ["part_path", "edge_ids", "radius"],
    },
), write=True)
async def run_feature_fillet(part_path: str, edge_ids: list, radius: float):
    …
```

Inside a plugin's `register(app, ctx)` function, tools can also be registered
directly on the `PluginContext`:

```python
from kerf_core.plugin import ToolSpec

ctx.tools.register(
    name="my_tool",
    spec=ToolSpec(name="my_tool", description="…", parameters={…}),
    handler=my_handler,
)
```

---

## Write vs. read filtering

Every tool is classified as either **read** or **write**. The classification
controls which users can invoke the tool:

- `write=False` (default): any member, including viewers, can call the tool.
- `write=True`: requires `editor` or higher role. Viewers receive
  `{"error": "…", "code": "FORBIDDEN"}`.

The executor in `packages/kerf-chat/src/kerf_chat/tools/executor.py` enforces
this before dispatching. Write classification is determined either by an
explicit `write=True` flag on the spec or by name convention (`set_`, `add_`,
`create_`, `delete_`, `run_`, `write_`, `edit_`, …).

---

## Tool error shape

Every tool returns a JSON-serialisable value. Errors are returned as:

```json
{"error": "human-readable message", "code": "SNAKE_CASE_CODE"}
```

Never as exceptions or 500 responses. The LLM reads the `error` and `code`
fields to decide how to recover. Common codes: `NOT_FOUND`, `BAD_ARGS`,
`FORBIDDEN`, `TIMEOUT`.

---

## The doc-search-first pattern

The ~150 tools are deliberately low-level (file read/write/edit, feature node
append, BIM element mutation). Before touching a non-`.jscad` file, the LLM
is expected to consult the authoring corpus:

1. `search_kerf_docs("fillet")` — full-text search across all loaded corpus
   docs. Returns `[{path, title, excerpt, score}]`.
2. `read_file("/docs/llm/feature.md")` — paths under `/docs/llm/` are routed
   to the in-memory corpus, not the project tree. Returns the doc content.
3. Armed with the right JSON schema and conventions, call `edit_file` to mutate
   the file directly.

This keeps the tool count stable: adding support for a new file kind means
writing a corpus doc in `llm_docs/`, not new tool functions.

### `search_kerf_docs`

```
search_kerf_docs(query: str) -> list[{path, title, excerpt, score}]
```

- Lives in `packages/kerf-chat/src/kerf_chat/tools/docs.py`
- Corpus is loaded at boot from every plugin that ships an `llm_docs/` folder
- Scoring is TF-IDF-style substring match; returns up to 8 results
- Called by the LLM before every unfamiliar file kind or feature type

**Plugins contributing to the corpus**

| Plugin | Corpus folder |
|--------|---------------|
| `kerf-chat` | `packages/kerf-chat/src/kerf_chat/llm_docs/` |
| `kerf-imports` | `packages/kerf-imports/src/kerf_imports/llm_docs/` |
| `kerf-bim` | `packages/kerf-bim/src/kerf_bim/llm_docs/` |
| `kerf-electronics` | `packages/kerf-electronics/src/kerf_electronics/llm_docs/` |
| `kerf-render` | `packages/kerf-render/src/kerf_render/llm_docs/` |

---

## Tool categories

Tools are grouped by domain. What follows is a map of which plugin module
contributes which tool surface. See [llm-tools.md](./llm-tools.md) for the
complete per-tool reference.

| Category | Plugin | Tool module |
|----------|--------|-------------|
| File ops | `kerf-api` | `tools/file_ops.py` |
| Object ops (duplicate, delete) | `kerf-api` | `tools/object_ops.py` |
| Scaffold (seed new file JSON) | `kerf-api` | `tools/scaffold.py` |
| Revisions (list, restore) | `kerf-api` | `tools/revisions.py` |
| Equations + configurations | `kerf-api` | `tools/equations.py`, `tools/configurations.py` |
| Validation | `kerf-api` | `tools/validation.py` |
| Layers + canvas | `kerf-api` | `tools/layers.py`, `tools/project_layers.py` |
| Doc search | `kerf-chat` | `tools/docs.py` |
| Sketch | `kerf-cad-core` | (registered from plugin) |
| Feature tree (pad, pocket, fillet, …) | `kerf-cad-core` | (registered from plugin) |
| Mesh + SubD + 3DM | `kerf-imports` | `tools/subd.py`, `tools/mesh.py`, `tools/import_3dm.py` |
| Curve ops | `kerf-imports` | `tools/curve_ops.py` |
| Drawings (hatches, leaders, dims) | `kerf-imports` | `tools/drawings.py` |
| Draft (2D entities + DXF export) | `kerf-imports` | `tools/draft.py` |
| Inspection + compare | `kerf-imports` | `tools/inspection.py` |
| Assembly + mates | `kerf-mates` | `tools/assembly.py`, `tools/mates.py` |
| Tolerance stack | `kerf-mates` | `tools/tolerance.py` |
| BIM (elements, families, schedules, views, sheets, stairs, railings, MEP, curtain walls) | `kerf-bim` | `tools/bim.py`, …10 modules |
| Electronics — schematic (ERC, buses, diff-pairs, hierarchy) | `kerf-electronics` | `tools/erc.py`, `tools/buses.py`, `tools/hier_schematic.py` |
| Electronics — PCB (routing, DRC, pours, net classes, length tuning, via stitching, shove router) | `kerf-electronics` | `tools/routing.py`, `tools/pcb_drc.py`, `tools/pcb_layer_tools.py`, … |
| FEA | `kerf-fem` | `tools/fem.py` |
| Simulation | `kerf-fem` | `tools/sim.py` |
| CAM | `kerf-cam` | `tools/cam.py` |
| Topology optimisation | `kerf-topo` | `tools/topo.py` |
| Render | `kerf-render` | `tools/render.py` |
| Materials | `kerf-cloud` | `tools/material.py` (cloud) |

---

## Adding a tool

1. Pick the plugin that owns the domain (or create one if adding a new plugin).
2. Create `packages/kerf-<name>/src/kerf_<name>/tools/my_tool.py`.
3. Decorate the async handler with `@register(ToolSpec(…), write=True/False)`.
4. Import and call `register(...)` from the plugin's `register(app, ctx)` in
   `plugin.py`, or use `ctx.tools.register(...)` directly.
5. Write a test that exercises the happy path and at least one error path.
6. If the tool touches a new file kind, add a doc in `llm_docs/` describing
   the JSON schema so `search_kerf_docs` returns useful guidance.

Plugin contract: `PluginContext.tools` is a `ToolRegistry` instance. See
`packages/kerf-core/src/kerf_core/plugin.py` for the full `PluginContext`
dataclass.

---

## Adding authoring docs

Drop a `.md` file in `packages/kerf-<name>/src/kerf_<name>/llm_docs/` and
restart the server. The boot sequence automatically discovers and loads all
`llm_docs/` folders from installed plugins. File names are used as the corpus
path (`/docs/llm/<filename>`).

---

See also: [llm-tools.md](./llm-tools.md) · [architecture.md § Tool registry](./architecture.md) · [contributing.md](./contributing.md)
