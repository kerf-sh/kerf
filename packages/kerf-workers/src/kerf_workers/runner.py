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
    fem_timeout: int = 300,
    sim_timeout: int = 300,
    tess_timeout: int = 300,
    cam_timeout: int = 300,
    auto_tess_timeout: int = 300,
    cloud_enabled: bool = False,
    local_mode: bool = True,
):
    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")

    own_pool = pool is None
    if own_pool:
        pool = await create_pool()

    workers = []

    for i in range(fem_count):
        workers.append(
            FEMWorker(
                pool=pool,
                storage_getter=storage_getter,
                pyworker_url=pyworker_url,
                timeout=fem_timeout,
            )
        )

    for i in range(sim_count):
        workers.append(
            SPICEWorker(
                pool=pool,
                storage_getter=storage_getter,
                pyworker_url=pyworker_url,
                timeout=sim_timeout,
            )
        )

    # tess_count and auto_tess_count both use AutoTessWorker (canonical since kerf-tess refactor)
    for i in range(tess_count + auto_tess_count):
        workers.append(
            AutoTessWorker(
                pool=pool,
                storage_getter=storage_getter,
                pyworker_url=pyworker_url,
                timeout=tess_timeout,
            )
        )

    for i in range(cam_count):
        workers.append(
            CAMWorker(
                pool=pool,
                storage_getter=storage_getter,
                pyworker_url=pyworker_url,
                timeout=cam_timeout,
            )
        )

    # CompactionWorker: cloud-tier only. _maybe_compaction_worker guards the gate.
    workers.extend(_maybe_compaction_worker(pool, cloud_enabled, local_mode, compaction_count))

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
            cloud_enabled=_cloud_enabled,
            local_mode=_local_mode,
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_workers())
