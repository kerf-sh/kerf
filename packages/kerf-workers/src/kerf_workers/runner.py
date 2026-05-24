import asyncio
import logging
import signal
import os
from typing import Optional

import asyncpg

from kerf_fem.worker import FEMWorker
from kerf_workers.spice_worker import SPICEWorker
from kerf_tess.worker import AutoTessWorker
from kerf_cam.worker import CAMWorker

logger = logging.getLogger(__name__)

# ── CompactionWorker (cloud-tier only; import lazily to avoid hard dep) ─────

def _maybe_compaction_worker(pool, cloud_enabled: bool, local_mode: bool, count: int):
    """
    Instantiate CompactionWorker instances if cloud_enabled and not local_mode.
    Returns an empty list when not in cloud mode so the caller can skip cleanly.
    """
    if not cloud_enabled or local_mode or count <= 0:
        return []
    try:
        from kerf_core.workers.compaction_worker import CompactionWorker  # type: ignore
        return [CompactionWorker(pool=pool, cloud_enabled=cloud_enabled, local_mode=local_mode) for _ in range(count)]
    except ImportError:
        logger.warning("kerf-workers: kerf_core not installed; skipping CompactionWorker")
        return []
    except Exception:
        logger.exception("kerf-workers: failed to create CompactionWorker")
        return []


# ── PricingRefreshWorker (model_prices from LiteLLM; lazy dep) ──────────────

def _maybe_pricing_worker(pool):
    """One PricingRefreshWorker — refreshes model_prices from LiteLLM at
    boot then daily. Runs in every mode: the chat model dropdown and
    billing both read model_prices, and a fresh/reset DB is EMPTY until
    this runs (was never wired into the harness → no models / no
    up-to-date pricing). Lazy import so a missing kerf-pricing doesn't
    break the worker set.
    """
    try:
        from kerf_pricing.worker import PricingRefreshWorker  # type: ignore
        return [PricingRefreshWorker(pool)]
    except ImportError:
        logger.warning("kerf-workers: kerf_pricing not installed; skipping PricingRefreshWorker")
        return []
    except Exception:
        logger.exception("kerf-workers: failed to create PricingRefreshWorker")
        return []


def _maybe_rate_limit_gc_worker(pool):
    """One RateLimitGCWorker — prunes rate_limit_buckets rows every 15 min.

    Lazy import so a missing kerf-core doesn't hard-fail the worker set.
    """
    try:
        from kerf_core.workers.rate_limit_gc_worker import RateLimitGCWorker  # type: ignore
        return [RateLimitGCWorker(pool)]
    except ImportError:
        logger.warning("kerf-workers: kerf_core not installed; skipping RateLimitGCWorker")
        return []
    except Exception:
        logger.exception("kerf-workers: failed to create RateLimitGCWorker")
        return []


def _maybe_cycles_workers(pool, count: int):
    """Instantiate CyclesWorker instances that drain the render_jobs table.

    Lazy import so a missing kerf-render doesn't hard-fail the worker set.
    Uses a dedicated async wrapper (:class:`_CyclesQueueWorker`) that follows
    the BaseWorker poll-loop pattern.

    The number of workers defaults to the ``CYCLES_WORKERS`` env var
    (default ``1``).  Set to ``0`` to disable.
    """
    if count <= 0:
        return []
    try:
        from kerf_render.queue_worker import CyclesQueueWorker  # type: ignore
        return [CyclesQueueWorker(pool=pool) for _ in range(count)]
    except ImportError:
        logger.warning("kerf-workers: kerf_render not installed; skipping CyclesQueueWorker")
        return []
    except Exception:
        logger.exception("kerf-workers: failed to create CyclesQueueWorker")
        return []


class DummyStorage:
    async def get(self, key: str):
        raise NotImplementedError("storage not configured")


async def create_pool() -> asyncpg.Pool:
    database_url = os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/kerf")
    return await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
    )


async def start_all_workers(
    pool: asyncpg.Pool,
    storage_getter,
    fem_count: int = 1,
    sim_count: int = 1,
    tess_count: int = 1,
    cam_count: int = 0,
    auto_tess_count: int = 0,
    compaction_count: int = 1,
    cycles_count: int = 1,
    fem_timeout: int = 300,
    sim_timeout: int = 300,
    tess_timeout: int = 300,
    cam_timeout: int = 300,
    auto_tess_timeout: int = 300,
    cloud_enabled: bool = False,
    local_mode: bool = True,
):
    own_pool = pool is None
    if own_pool:
        pool = await create_pool()

    workers = _build_workers(
        pool, storage_getter,
        fem_count=fem_count, sim_count=sim_count, tess_count=tess_count,
        cam_count=cam_count, auto_tess_count=auto_tess_count,
        compaction_count=compaction_count,
        cycles_count=cycles_count,
        fem_timeout=fem_timeout, sim_timeout=sim_timeout,
        tess_timeout=tess_timeout, cam_timeout=cam_timeout,
        cloud_enabled=cloud_enabled, local_mode=local_mode,
    )

    if not workers:
        logger.info("no workers configured")
        return

    logger.info(f"starting {len(workers)} worker(s)")

    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("received shutdown signal")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    async with asyncio.TaskGroup() as tg:
        for worker in workers:
            tg.create_task(worker.run(tg))

        await shutdown_event.wait()
        for worker in workers:
            worker.stop()

    logger.info("all workers stopped")

    if own_pool:
        await pool.close()


def _build_workers(
    pool: asyncpg.Pool,
    storage_getter,
    *,
    fem_count: int = 1,
    sim_count: int = 1,
    tess_count: int = 1,
    cam_count: int = 0,
    auto_tess_count: int = 0,
    compaction_count: int = 1,
    cycles_count: int = 1,
    fem_timeout: int = 300,
    sim_timeout: int = 300,
    tess_timeout: int = 300,
    cam_timeout: int = 300,
    cloud_enabled: bool = False,
    local_mode: bool = True,
) -> list:
    """Construct the configured worker instances (no lifecycle)."""
    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    workers: list = []
    for _ in range(fem_count):
        workers.append(FEMWorker(pool=pool, storage_getter=storage_getter,
                                 pyworker_url=pyworker_url, timeout=fem_timeout))
    for _ in range(sim_count):
        workers.append(SPICEWorker(pool=pool, storage_getter=storage_getter,
                                   pyworker_url=pyworker_url, timeout=sim_timeout))
    # tess_count and auto_tess_count both use AutoTessWorker.
    for _ in range(tess_count + auto_tess_count):
        workers.append(AutoTessWorker(pool=pool, storage_getter=storage_getter,
                                      pyworker_url=pyworker_url, timeout=tess_timeout))
    for _ in range(cam_count):
        workers.append(CAMWorker(pool=pool, storage_getter=storage_getter,
                                 pyworker_url=pyworker_url, timeout=cam_timeout))
    # CompactionWorker: cloud-tier only; _maybe_compaction_worker gates it.
    workers.extend(_maybe_compaction_worker(pool, cloud_enabled, local_mode, compaction_count))
    # PricingRefreshWorker: keeps model_prices current (boot + daily) so
    # the chat model dropdown + billing work.
    workers.extend(_maybe_pricing_worker(pool))
    # RateLimitGCWorker: prunes rate_limit_buckets rows older than 24h.
    workers.extend(_maybe_rate_limit_gc_worker(pool))
    # CyclesQueueWorker: drains render_jobs table (kerf-render); lazy import.
    workers.extend(_maybe_cycles_workers(pool, cycles_count))
    return workers


class InProcessWorkers:
    """Run the worker harness inside the API process.

    Lets one app instance serve HTTP *and* drain the job queues, so
    scaling the app scales workers — no separate worker app/machine.
    Unlike start_all_workers() this installs NO OS signal handlers: the
    host process (uvicorn) owns SIGTERM/SIGINT; the FastAPI lifespan
    drives shutdown via aclose().
    """

    def __init__(self, task, stop_event, workers):
        self._task = task
        self._stop_event = stop_event
        self._workers = workers

    @classmethod
    async def start(cls, pool: asyncpg.Pool, storage_getter, **kwargs) -> "InProcessWorkers":
        workers = _build_workers(pool, storage_getter, **kwargs)
        if not workers:
            logger.info("inprocess workers: none configured")
            return cls(None, None, [])
        logger.info("inprocess workers: starting %d", len(workers))
        stop_event = asyncio.Event()

        async def _run():
            try:
                async with asyncio.TaskGroup() as tg:
                    for w in workers:
                        tg.create_task(w.run(tg))
                    await stop_event.wait()
                    for w in workers:
                        w.stop()
            except asyncio.CancelledError:
                for w in workers:
                    w.stop()
                raise

        return cls(asyncio.create_task(_run()), stop_event, workers)

    async def aclose(self, timeout: float = 30.0) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("inprocess workers: stop timed out; cancelled")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("inprocess workers: error during shutdown")
        logger.info("inprocess workers: stopped")


async def run_workers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pool = await create_pool()

    def get_storage():
        return DummyStorage()

    _cloud_enabled = os.getenv("CLOUD_ENABLED", "false").lower() in ("1", "true", "yes")
    _local_mode = os.getenv("LOCAL_MODE", "true").lower() in ("1", "true", "yes")

    try:
        await start_all_workers(
            pool=pool,
            storage_getter=get_storage,
            fem_count=int(os.getenv("FEM_WORKERS", "1")),
            sim_count=int(os.getenv("SIM_WORKERS", "1")),
            tess_count=int(os.getenv("TESS_WORKERS", "1")),
            cam_count=int(os.getenv("CAM_WORKERS", "0")),
            compaction_count=int(os.getenv("COMPACTION_WORKERS", "1")),
            cycles_count=int(os.getenv("CYCLES_WORKERS", "1")),
            cloud_enabled=_cloud_enabled,
            local_mode=_local_mode,
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_workers())
