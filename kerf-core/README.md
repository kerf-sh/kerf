# kerf-core

The Kerf core package. Provides the FastAPI application factory, plugin loader, and shared infrastructure (config, storage, db pool, dependency injection helpers) for all Kerf plugins.

## Install

```
pip install -e ./packages/kerf-core[dev]
```

## Run

```
kerf-server --config kerf.toml
# or
python -m kerf_core
```

## Plugin contract

All Kerf plugins implement `async def register(app, ctx) -> PluginManifest` registered under the `kerf.plugins` entry-point group. See `kerf_core.plugin` for the contract types.
