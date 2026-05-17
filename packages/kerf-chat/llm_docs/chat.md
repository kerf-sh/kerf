# kerf-chat — LLM agent loop plugin

`kerf-chat` is the plugin that hosts the conversational CAD agent. It mounts the `/api/projects/{id}/chat` SSE endpoint, drives the agent loop (tool dispatch, billing integration, prompt-cache warm-up), and registers the `search_kerf_docs` tool that the agent uses to look up file-format authoring guides.

Depends on `kerf-api`. Provides `chat.llm`, `chat.tools-dispatch`, and `chat.search-docs`.

---

## Plugin registration

```python
# kerf_chat/plugin.py
PLUGIN_DEPENDS = ["kerf-api"]

async def register(app, ctx) -> PluginManifest:
    from kerf_chat import llm as _llm
    app.include_router(_llm.router, prefix="/api", tags=["chat"])
    _register_tools(ctx)   # registers search_kerf_docs
    return PluginManifest(
        name="kerf-chat",
        version="0.1.0",
        provides=["chat.llm", "chat.tools-dispatch", "chat.search-docs"],
        depends=["kerf-api"],
    )
```

---

## Agent loop (`kerf_chat.llm`)

The agent loop implements a streaming ReAct-style tool-use cycle:

1. Build system prompt (includes project type, active file list, available tool specs)
2. `kerf-billing`: `load_user_billing`, `load_model_info`, `pick_bucket` — or 402
3. Stream LLM response as SSE events (`text`, `tool_use`, `tool_result`, `done`)
4. For each `tool_use` block: look up handler in `ctx.tools`, run it, stream result
5. Feed tool results back into the LLM context for the next turn
6. After last token: `commit_spend` with actual input/output token counts

Prompt caching is enabled via `ANTHROPIC_PROMPT_CACHE=true` (default). The system prompt and docs corpus are marked as cacheable to reduce latency on repeated turns.

### SSE event types

| Event | Payload |
|---|---|
| `text` | `{delta: "..."}` — streamed text token |
| `tool_use` | `{id, name, input}` — tool invocation starting |
| `tool_result` | `{tool_use_id, result}` — tool result from handler |
| `error` | `{message, code}` — fatal error (e.g. 402 insufficient credits) |
| `done` | `{usage: {input_tokens, output_tokens}}` — stream complete |

---

## `search_kerf_docs` tool

The agent's built-in knowledge-base search tool. Performs keyword matching across all files in `kerf-chat/llm_docs/` and returns the top matching page names with a summary.

```json
{
  "name": "search_kerf_docs",
  "description": "Search the Kerf authoring guides for a topic (file format, tool, concept).",
  "parameters": {
    "query": {"type": "string"}
  }
}
```

The agent calls this whenever it needs to work on a non-`.jscad` file kind (sketch, feature, assembly, drawing, part, circuit, bim, etc.) before editing.

Search is backed by `kerf_chat.tools.docs` — a lightweight TF-IDF index built from the `llm_docs/` directory at startup. No external search service is required.

---

## System prompt overview

The system prompt establishes:

- Vocabulary lock: Part / Object / Component (see `index.md`)
- Workflow: read before edit, consult authoring guides for non-JSCAD files
- File-kind → extension mapping (`.jscad`, `.sketch`, `.assembly`, `.drawing`, `.feature`, `.part`, `.circuit.tsx`, `.step`)
- Strict rules: never create files when editing would work; always read first; no pastebacks

The full prompt text is in `kerf_chat.llm.SystemPrompt`.

---

## Authoring corpus

The `llm_docs/` directory IS the authoring corpus. The agent loads it as the search index. Key pages:

| Page | Covers |
|---|---|
| `index.md` | Corpus index and lookup workflow |
| `sketch.md` | `.sketch` geometry + constraint schema |
| `feature.md` | `.feature` OCCT feature tree schema |
| `assembly.md` | `.assembly` component placement schema |
| `drawing.md` | `.drawing` 2D sheet + dimensions schema |
| `part.md` | `.part` library metadata schema |
| `circuit.md` | `.circuit.tsx` tscircuit schema |
| `configurations.md` | Per-file variant overrides |
| `email.md` | Transactional email (cloud only — operator/support use) |
| `canvas.md` | Project canvas layers + display modes |

All other pages in `llm_docs/` (BIM, CAM, electronics, jewelry, FEM, etc.) are reachable via `search_kerf_docs`.

---

## Readme generator (`kerf_chat.readme_gen`)

A utility module that auto-generates `README.md` files for Workshop submissions. Called by the `generate_workshop_readme` LLM tool. Uses the project's file tree, BOM, and description to produce a structured Markdown file. Not part of the conversational loop.

---

## Integration points

- **kerf-billing**: the billing loop wraps every LLM call — see `billing.md` for the three-bucket model
- **kerf-api `ctx.tools`**: all tools registered by other plugins (CAM, FEM, BIM, render, etc.) are available to the agent via the tool registry
- **kerf-auth**: every `/api/projects/{id}/chat` request requires a valid JWT or API token
- **kerf-workers**: long-running operations (CAM, FEM, topo) use the job-queue pattern; the agent polls via `cam_job_status` / `fem_job_status` tools
