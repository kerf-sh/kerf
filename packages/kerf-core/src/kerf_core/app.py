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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from kerf_core.config import Config
from kerf_core.plugin import (
    PluginContext,
    PluginManifest,
    ToolRegistry,
    WorkerRegistry,
)
from kerf_core.storage.factory import create_storage as _create_storage
from kerf_core.storage import set_storage as _set_storage
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

# Default 200 MB; configurable via KERF_MAX_BODY_BYTES.
_DEFAULT_MAX_BODY_BYTES = 200 * 1024 * 1024


class _BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the configured cap.

    Uses the Content-Length header for a fast early reject (before reading
    the body). Streaming uploads without Content-Length are not checked here;
    they are bounded at the application layer (chunked-upload routes).
    """

    def __init__(self, app, max_bytes: int = _DEFAULT_MAX_BODY_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    return JSONResponse(
                        {"detail": f"Request body too large (max {self.max_bytes} bytes)"},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)


def create_app(config: Config | None = None, config_path: str = "") -> FastAPI:
    """Create and return a fully-configured FastAPI application."""
    if config is None:
        config = Config.load(config_path)

    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _load_plugins(app, config)
        # Register the SPA catch-all LAST — after plugin routers mount
        # their /api, /auth, /v1 routes. Starlette matches in
        # registration order, so mounting the frontend earlier would
        # shadow every plugin API route with the SPA fallback.
        _mount_frontend(app)
        worker_handle = await _maybe_start_inprocess_workers(app)
        yield
        if worker_handle is not None:
            await worker_handle.aclose()
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

    try:
        _max_body = int(os.environ.get("KERF_MAX_BODY_BYTES", "") or _DEFAULT_MAX_BODY_BYTES)
    except (ValueError, TypeError):
        _max_body = _DEFAULT_MAX_BODY_BYTES
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=_max_body)

    app.state.config = config
    app.state.loaded_plugins: list[PluginManifest] = []

    _mount_health(app)
    # _mount_frontend is called from the lifespan AFTER plugins load
    # (see lifespan above) so the SPA catch-all doesn't shadow /api/*.

    return app


async def _maybe_start_inprocess_workers(app: FastAPI):
    """Co-locate the worker harness in the API process.

    When KERF_INPROCESS_WORKERS is truthy (the hosted single-app deploy:
    one machine runs engine + workers, so scaling the app scales
    workers) the worker harness runs as background tasks sharing this
    process's DB pool and storage. Failing to start workers must NOT
    prevent the API from booting — log and continue.
    """
    flag = os.getenv("KERF_INPROCESS_WORKERS", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return None
    pool = getattr(app.state, "pool", None)
    if pool is None:
        logger.warning("inprocess_workers_skipped_no_pool")
        return None
    try:
        from kerf_workers.runner import InProcessWorkers

        cloud_enabled = os.getenv("CLOUD_ENABLED", "false").lower() in ("1", "true", "yes")
        local_mode = os.getenv("LOCAL_MODE", "true").lower() in ("1", "true", "yes")
        handle = await InProcessWorkers.start(
            pool=pool,
            storage_getter=lambda: getattr(app.state, "storage", None),
            fem_count=int(os.getenv("FEM_WORKERS", "1")),
            sim_count=int(os.getenv("SIM_WORKERS", "1")),
            tess_count=int(os.getenv("TESS_WORKERS", "1")),
            cam_count=int(os.getenv("CAM_WORKERS", "0")),
            compaction_count=int(os.getenv("COMPACTION_WORKERS", "1")),
            cloud_enabled=cloud_enabled,
            local_mode=local_mode,
        )
        logger.info("inprocess_workers_started")
        return handle
    except Exception as exc:
        logger.warning("inprocess_workers_failed", error=str(exc))
        return None


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
        # Real backend routes (incl. /auth/google/*, /auth/github/login/*)
        # are registered before this fallback and match first. Unmatched
        # api/v1/health paths should 404 as JSON (API clients expect that);
        # but /auth/* also contains *client* routes like /auth/callback
        # (the post-OAuth landing page) which must get the SPA shell.
        if full_path.startswith(("api/", "v1/", "health", "healthz")):
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
    # Initialise the module-level storage singleton too. Handlers call
    # get_storage_required() (the singleton), not app.state.storage —
    # without this every storage-touching endpoint (chat-with-parts,
    # thumbnails for ALL kinds, uploads, derived artifacts) 500s with
    # "Storage not initialized". set_storage() was never called anywhere.
    _set_storage(storage)

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
