# Plugin development

How to write a Kerf plugin: a self-contained Python package that mounts routes,
registers LLM tools, and advertises capability tags.

## Overview

Every feature domain in Kerf lives in a plugin (`packages/kerf-<name>/`). At
server boot `importlib.metadata.entry_points(group="kerf.plugins")` discovers
every installed plugin in the active virtualenv, calls each plugin's
`register(app, ctx)` function in dependency order, and aggregates the returned
`PluginManifest` objects onto `app.state.loaded_plugins`.

Plugins are plain Python packages — no framework magic, no generated code.

## Plugin layout

```
packages/kerf-myplugin/
├── pyproject.toml               # name, version, entry-point, deps
├── src/kerf_myplugin/
│   ├── __init__.py
│   ├── plugin.py                # register(app, ctx) → PluginManifest
│   ├── routes.py                # FastAPI router (optional)
│   ├── tools/                   # LLM-tool modules (optional)
│   │   └── my_tools.py
│   └── llm_docs/                # Markdown docs indexed by search_kerf_docs (optional)
│       └── my_topic.md
└── tests/
    └── test_my_plugin.py
```

Library plugins (no routes, no tools — pure Python API) may omit `routes.py`
and `tools/` entirely.

## pyproject.toml

```toml
[project]
name = "kerf-myplugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["kerf-core"]     # always depend on kerf-core

[project.entry-points."kerf.plugins"]
myplugin = "kerf_myplugin.plugin:register"
```

The entry-point key (`myplugin`) is the name used in `PluginManifest.depends`
by other plugins that need this one to be loaded first.

Add the package to the root `pyproject.toml` workspace:

```toml
# root pyproject.toml
[tool.uv.workspace]
members = [
    ...
    "packages/kerf-myplugin",
]

[tool.uv.sources]
kerf-myplugin = { workspace = true }
```

Add it to the relevant persona optional-dependency groups:

```toml
[project.optional-dependencies]
mech = [
    ...
    "kerf-myplugin",
]
```

## The PluginContext contract

`register(app, ctx)` receives:

```python
@dataclass
class PluginContext:
    pool: asyncpg.Pool          # shared Postgres connection pool
    storage: StorageBackend     # storage backend (local/s3/filesystem)
    config: Config              # parsed kerf.toml
    tools: ToolRegistry         # shared LLM tool registry
    workers: WorkerRegistry     # shared background-worker registry
    logger: structlog.BoundLogger
    cloud_enabled: bool         # True when [cloud].enabled = true
    local_mode: bool            # True when [server].local_mode = true
```

Never store `app` or `ctx` as module-level globals. If your routes need
database access, use FastAPI dependency injection (`request.app.state`) or
pass the pool through request state.

## The PluginManifest contract

```python
@dataclass
class PluginManifest:
    name: str                   # matches the entry-point key
    version: str                # semver string
    provides: list[str] = []    # capability tags this plugin adds
    depends: list[str] = []     # plugin names that must register first
```

`provides` is the source of truth for `GET /health/capabilities`. Use tags
from the taxonomy in [capabilities.md](./capabilities.md) when they fit; invent
new namespaced tags for genuinely new capabilities.

## Minimal plugin.py

```python
# packages/kerf-myplugin/src/kerf_myplugin/plugin.py
from __future__ import annotations
import logging
from fastapi import FastAPI
from kerf_core.plugin import PluginContext, PluginManifest

logger = logging.getLogger(__name__)

PLUGIN_DEPENDS = ["kerf-api"]   # informational; use PluginManifest.depends


async def register(app: FastAPI, ctx: PluginContext) -> PluginManifest:
    # Mount routes
    from kerf_myplugin.routes import router
    app.include_router(router, prefix="/myplugin", tags=["myplugin"])

    # Register LLM tools
    _register_tools(ctx)

    logger.info("kerf-myplugin: registered")

    return PluginManifest(
        name="myplugin",
        version="0.1.0",
        provides=["myplugin.feature-a"],
        depends=["kerf-api"],
    )


def _register_tools(ctx: PluginContext) -> None:
    import importlib
    tool_modules = ["kerf_myplugin.tools.my_tools"]
    for path in tool_modules:
        try:
            mod = importlib.import_module(path)
            _register_module_tools(ctx, mod, path)
        except Exception as exc:
            logger.warning("kerf-myplugin: failed to load %s: %s", path, exc)


def _register_module_tools(ctx, mod, module_path: str) -> None:
    """Register (spec, handler) pairs from a tool module into ctx.tools."""
    attrs = dir(mod)
    spec_vars = {
        name[:-5]: getattr(mod, name)
        for name in attrs
        if name.endswith("_spec") and hasattr(getattr(mod, name), "name")
    }
    for base_name, spec in spec_vars.items():
        handler = getattr(mod, f"run_{base_name}", None)
        if handler is None:
            continue
        try:
            ctx.tools.register(spec.name, spec, handler)
        except ValueError:
            pass  # already registered
```

## Capability tags

Tags are dotted namespaced strings. Use the existing taxonomy from
[capabilities.md](./capabilities.md) when a tag already fits. For a new plugin,
add new tags under a namespace that matches your plugin's domain:

```python
provides=["myplugin.feature-a", "myplugin.feature-b"]
```

The frontend and other plugins check `GET /health/capabilities` to gate
behaviour on whether a tag is present. A plugin that loads but whose heavy
deps are missing should return `provides=[]` rather than raising — it is then
listed as "dormant" rather than absent.

## Registering tools directly (without the discovery pattern)

If you prefer to register tools explicitly rather than via the
`_spec` / `run_` naming convention:

```python
from kerf_core.plugin import ToolSpec

spec = ToolSpec(
    name="my_tool",
    description="Does something useful.",
    parameters={
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "Input value."},
        },
        "required": ["value"],
    },
)

async def my_handler(ctx, args: bytes) -> str:
    import json
    from kerf_chat.tools.registry import ok_payload, err_payload
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"bad args: {e}", "BAD_ARGS")
    return ok_payload({"result": a["value"] * 2})

ctx.tools.register("my_tool", spec, my_handler)
```

For the `@register` decorator pattern used by most tools, see
[llm-tool-authoring.md](./llm-tool-authoring.md).

## Background workers

Register a long-running worker factory:

```python
async def my_worker_factory():
    import asyncio
    async def loop():
        while True:
            # poll a queue, process jobs
            await asyncio.sleep(5)
    return asyncio.create_task(loop())

ctx.workers.register("myplugin.worker", my_worker_factory)
```

Workers are started by `ctx.workers.start_all()` after all plugins register.

## LLM docs corpus

Drop Markdown files into `llm_docs/` inside your package. They are
automatically indexed by the `search_kerf_docs` tool at boot. The LLM
consults this corpus before authoring or editing files of the kinds your
plugin introduces.

```
kerf_myplugin/llm_docs/my_file_kind.md
```

Name the file after the file kind it documents (e.g. `myformat.md`). Keep
the content concise — the tool returns the full file as context.

## Testing

Add a `tests/` directory at the package root:

```
packages/kerf-myplugin/tests/
└── test_my_plugin.py
```

The root `pyproject.toml` `testpaths` list must include your test directory.
For new plugins, add:

```toml
[tool.pytest.ini_options]
testpaths = [
    ...
    "packages/kerf-myplugin/tests",
]
```

Tests run with `pytest` from the repo root.

## See also

- [llm-tool-authoring.md](./llm-tool-authoring.md) — `@register` pattern, ok/err payloads
- [capabilities.md](./capabilities.md) — full capability tag taxonomy
- [architecture.md](./architecture.md) — boot sequence in detail
- [persona-bundles.md](./persona-bundles.md) — adding a plugin to a persona
