import asyncio
import logging
import signal
import time
import os
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db.connection import create_pool, close_pool, get_pool
from storage import create_storage, set_storage
from workers.runner import start_all_workers

import tools.file_ops
import tools.object_ops
import tools.assembly
import tools.surfacing
import tools.topo
import tools.material
import tools.scaffold
import tools.revisions
import tools.configurations
import tools.equations
import tools.validation
import tools.tolerance
import tools.docs
import tools.autoroute
import tools.fem
import tools.cam
import tools.sim
import tools.rf
import tools.sketch

import routes.auth as auth
import routes.api as api
import routes.v1 as v1
import routes.cloud as cloud
import routes.billing as billing

settings = get_settings()
logger = logging.getLogger(__name__)

storage = None
shutdown_event = asyncio.Event()
workers_task = None
mailer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, workers_task, mailer

    from db.connection import create_pool, close_pool
    await create_pool()

    storage = create_storage(
        backend=settings.storage_backend,
        s3_bucket=settings.s3_bucket,
        s3_region=settings.s3_region,
        s3_access_key_id=settings.s3_access_key_id,
        s3_secret_access_key=settings.s3_secret_access_key,
        s3_endpoint=settings.s3_endpoint,
        s3_public_url_base=settings.s3_public_url_base,
        cdn_base_url=settings.cdn_base_url,
        local_storage_path=settings.local_storage_path,
    )
    set_storage(storage)

    workers_task = asyncio.create_task(
        start_all_workers(
            pool=get_pool(),
            storage_getter=lambda: storage,
            fem_count=int(os.getenv("FEM_WORKERS", "1")),
            sim_count=int(os.getenv("SIM_WORKERS", "1")),
            tess_count=int(os.getenv("TESS_WORKERS", "1")),
            cam_count=int(os.getenv("CAM_WORKERS", "0")),
        )
    )

    logger.info(f"Storage backend: {settings.storage_backend}")
    logger.info(f"Cloud enabled: {settings.cloud_enabled}")
    logger.info(f"Local mode: {settings.local_mode}")

    if settings.cloud_enabled:
        from cloud.email.mailer import Mailer
        mailer = Mailer(pool=get_pool(), cfg=settings)
        await mailer.boot()
        logger.info("Email service started")

        from distributors.registry import Registry as DistributorRegistry, set_registry
        from distributors.sync import start_sweep as start_distributor_sweep
        _dist_registry = DistributorRegistry(pool=get_pool(), cfg=settings)
        await _dist_registry.reload()
        set_registry(_dist_registry)
        asyncio.create_task(start_distributor_sweep(get_pool(), _dist_registry))
        logger.info("Distributor registry loaded")

    yield

    logger.info("Shutting down workers...")
    shutdown_event.set()
    if workers_task:
        try:
            await asyncio.wait_for(workers_task, timeout=30)
        except asyncio.TimeoutError:
            pass
    if mailer:
        await mailer.shutdown()
        logger.info("Email service stopped")
    await close_pool()
    logger.info("Shutdown complete")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "%s %s %d %.1fms request_id=%s",
            request.method, request.url.path,
            response.status_code, duration_ms, request_id,
        )
        return response


class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=60.0)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"error": "gateway timeout"})


app = FastAPI(title="Kerf API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(TimeoutMiddleware)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "env": settings.env}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/api/config")
async def get_config():
    return {
        "google_client_id": settings.google_client_id,
        "cloud_enabled": settings.cloud_enabled,
        "local_mode": settings.local_mode,
        "default_model": settings.default_model,
    }


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.api_tokens_router, prefix="/api", tags=["api-tokens"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(v1.router, prefix="/v1", tags=["v1"])

if settings.cloud_enabled:
    app.include_router(cloud.router, prefix="/api", tags=["cloud"])
    app.include_router(cloud.github_oauth_router, prefix="/auth", tags=["github-oauth"])
    app.include_router(billing.router, prefix="/api", tags=["billing"])

# Serve the compiled SPA. Must come AFTER all include_router calls so API
# routes are not shadowed. The html=True flag enables SPA fallback routing
# (index.html is returned for unknown paths, letting React Router handle them).
_spa_dir = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_spa_dir):
    app.mount("/", StaticFiles(directory=_spa_dir, html=True), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"error": "server error"})


def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


if __name__ == "__main__":
    import uvicorn

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(settings.port),
        log_level="info",
        timeout_graceful_shutdown=30,
    )
