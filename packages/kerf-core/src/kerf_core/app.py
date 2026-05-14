"""Kerf FastAPI application factory.

``create_app()`` is the single entrypoint.  It:

1. Loads config from kerf.toml (or defaults).
2. Opens an asyncpg pool.
3. Wires storage, tool registry, and worker registry.
4. Scans the ``kerf.plugins`` entry-points group.
5. Topologically sorts discovered plugins by their ``depends`` declarations.
6. Calls each plugin's ``register(app, ctx)`` in dependency order.
7. Mounts ``/health/capabilities`` reporting loaded plugins.
8. Returns the configured ``FastAPI`` instance.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from kerf_core.config import Config
from kerf_core.plugin import (
    PluginContext,
    PluginManifest,
    ToolRegistry,
    WorkerRegistry,
)
from kerf_core.storage.factory import create_storage as _create_storage
from kerf_core.utils.topo_sort import topo_sort


def _wire_storage(config):
    return _create_storage(
        backend=config.storage_backend,
        s3_bucket=config.s3_bucket,
        s3_region=config.s3_region,
        s3_access_key_id=config.s3_access_key_id,
        s3_secret_access_key=config.s3_secret_access_key,
        s3_endpoint=config.s3_endpoint,
        s3_public_url_base=config.s3_public_url_base,
        cdn_base_url=config.cdn_base_url,
        local_storage_path=config.local_storage_path,
    )


logger: structlog.BoundLogger = structlog.get_logger("kerf_core.app")


def create_app(config: Config | None = None, config_path: str = "") -> FastAPI:
    """Create and return a fully-configured FastAPI application."""
    if config is None:
        config = Config.load(config_path)

    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _load_plugins(app, config)
        yield
        pool = getattr(app.state, "pool", None)
        if pool is not None:
            await pool.close()

    app = FastAPI(
        title="Kerf",
        version="0.1.0",
        description="Chat-driven CAD / EDA / BIM platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.cors_origin, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config = config
    app.state.loaded_plugins: list[PluginManifest] = []

    _mount_health(app)
    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built Vite SPA from /app/dist (or KERF_FRONTEND_DIST).

    Skipped when the directory is missing (dev runs Vite separately on :5173;
    Docker builds embed dist/ at /app/dist).
    """
    dist_dir = os.environ.get("KERF_FRONTEND_DIST", "/app/dist")
    dist_path = Path(dist_dir)
    if not dist_path.is_dir() or not (dist_path / "index.html").exists():
        return

    # Static assets at /assets/, /favicon.svg, etc.
    app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API routes are matched first by FastAPI's router; this catches
        # everything else and serves the SPA shell so React Router can
        # handle client-side routes.
        if full_path.startswith(("api/", "auth/", "v1/", "health", "healthz")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        target = dist_path / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(dist_path / "index.html")


async def _load_plugins(app: FastAPI, config: Config) -> None:
    """Discover, sort, and register all kerf.plugins entry-points."""
    pool: Any = None
    if config.database_url:
        try:
            from kerf_core.db.connection import create_pool_from_config
            pool = await create_pool_from_config(config)
            app.state.pool = pool
        except Exception as exc:
            logger.warning("db_pool_failed", error=str(exc))

    storage = _wire_storage(config)
    app.state.storage = storage

    tools = ToolRegistry()
    workers = WorkerRegistry()
    app.state.tools = tools
    app.state.workers = workers

    eps = _discover_entry_points()
    logger.info("plugins_discovered", count=len(eps), names=list(eps.keys()))

    register_fns: dict[str, Any] = {}
    for ep_name, ep in eps.items():
        try:
            register_fns[ep_name] = ep.load()
        except Exception as exc:
            logger.error("plugin_import_failed", plugin=ep_name, error=str(exc))

    if not register_fns:
        logger.info("no_plugins_registered")
        return

    edges: dict[str, list[str]] = {}
    for name in register_fns:
        fn = register_fns[name]
        mod = getattr(fn, "__module__", "")
        depends: list[str] = []
        try:
            mod_obj = importlib.import_module(mod)
            depends = getattr(mod_obj, "PLUGIN_DEPENDS", [])
        except Exception:
            pass
        edges[name] = depends

    sorted_names = topo_sort(list(register_fns.keys()), edges)
    sorted_names = [n for n in sorted_names if n in register_fns]

    loaded: list[PluginManifest] = []
    for name in sorted_names:
        fn = register_fns[name]
        plugin_logger = structlog.get_logger(f"plugin.{name}")
        ctx = PluginContext(
            pool=pool,
            storage=storage,
            config=config,
            tools=tools,
            workers=workers,
            logger=plugin_logger,
            cloud_enabled=config.cloud_enabled,
            local_mode=config.local_mode,
        )
        try:
            manifest: PluginManifest = await fn(app, ctx)
            loaded.append(manifest)
            logger.info(
                "plugin_loaded",
                name=manifest.name,
                version=manifest.version,
                provides=manifest.provides,
            )
        except Exception as exc:
            logger.error("plugin_register_failed", plugin=name, error=str(exc))

    app.state.loaded_plugins = loaded
    await workers.start_all()


def _discover_entry_points() -> dict[str, Any]:
    try:
        eps = importlib.metadata.entry_points(group="kerf.plugins")
        return {ep.name: ep for ep in eps}
    except Exception as exc:
        logger.warning("entry_point_discovery_failed", error=str(exc))
        return {}


def _mount_health(app: FastAPI) -> None:
    try:
        _kerf_version = importlib.metadata.version("kerf-core")
    except importlib.metadata.PackageNotFoundError:
        _kerf_version = "0.1.0"

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": _kerf_version}

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        return {"status": "ok", "version": _kerf_version}

    @app.get("/health/capabilities", tags=["health"])
    async def capabilities() -> JSONResponse:
        loaded: list[PluginManifest] = getattr(app.state, "loaded_plugins", [])
        all_caps: set[str] = set()
        plugins_data = []
        for m in loaded:
            all_caps.update(m.provides)
            plugins_data.append(
                {
                    "name": m.name,
                    "version": m.version,
                    "provides": m.provides,
                    "depends": m.depends,
                }
            )
        return JSONResponse(
            {
                "version": _kerf_version,
                "plugins": plugins_data,
                "capabilities": sorted(all_caps),
            }
        )


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    logging.basicConfig(level=logging.INFO)
