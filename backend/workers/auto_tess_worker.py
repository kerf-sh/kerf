"""
AutoTessWorker — PG LISTEN/NOTIFY-based tessellation job worker.

This worker extends BaseWorker to process ``step_tessellation_jobs`` rows that
are in ``status='queued'``. It differs from TessWorker in that it is woken up
by PostgreSQL NOTIFY on the ``step_file_uploaded`` channel rather than pure
polling. A long poll interval is used because the worker primarily relies on
the NOTIFY signal; the poll is a fallback for missed notifications or
startup.

The worker only processes jobs for workspaces that belong to the ``cloud`` tier.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import asyncpg

from workers.base import BaseWorker
from workers.tess_worker import TessDriver, TessInputSpec


logger = logging.getLogger(__name__)


async def notify_step_uploaded(conn: asyncpg.Connection, file_id: str) -> None:
    """
    Send a PG NOTIFY on the ``step_file_uploaded`` channel with the given
    file_id as the payload.

    This function is called from the upload-finalise path in the API to signal
    the AutoTessWorker that a new step file is ready for tessellation.

    Parameters
    ----------
    conn : asyncpg.Connection
        An active database connection.
    file_id : str
        The UUID of the newly uploaded step file (as a string).
    """
    await conn.execute("SELECT pg_notify('step_file_uploaded', $1)", file_id)


class AutoTessWorker(BaseWorker):
    """
    A worker that processes queued tessellation jobs using PG LISTEN/NOTIFY.

    It claims rows from ``step_tessellation_jobs`` that are ``status='queued'``
    for cloud-tier workspaces only. Jobs that have been stuck in ``'running'``
    for more than 10 minutes are re-queued as a safety measure.
    """

    name = "auto_tess"

    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter: Callable,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 30.0,
        timeout: int = 300,
    ) -> None:
        super().__init__(self.name, pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = TessDriver(pyworker_url=pyworker_url, timeout=timeout)
        self.timeout = timeout
        self._notify_event = asyncio.Event()
        self._listener_task: Optional[asyncio.Task] = None

    # -------------------------------------------------------------------------
    # BaseWorker interface
    # -------------------------------------------------------------------------

    async def run_one(self) -> bool:
        """
        Attempt to claim and process one tessellation job.

        Returns True if a job was found and processed (or failed), False if
        no jobs were available.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
                    FROM step_tessellation_jobs j
                    JOIN files f ON f.id = j.file_id
                    JOIN projects p ON p.id = f.project_id
                    JOIN workspaces w ON w.id = p.workspace_id
                    WHERE j.status = 'queued'
                      AND w.tier = 'cloud'
                      AND f.deleted_at IS NULL
                    ORDER BY j.created_at ASC
                    FOR UPDATE OF j SKIP LOCKED
                    LIMIT 1
                    """
                )
                if row is None:
                    return False

                job_id: str = row["id"]
                file_id: str = row["file_id"]
                storage_key: str = row["storage_key"]
                input_spec_raw = row["input_spec"]

                if not storage_key:
                    await conn.execute(
                        """
                        UPDATE step_tessellation_jobs
                        SET status = 'error', error = 'file has no storage_key',
                            finished_at = now()
                        WHERE id = $1
                        """,
                        job_id,
                    )
                    return True

                await conn.execute(
                    """
                    UPDATE step_tessellation_jobs
                    SET status = 'running', started_at = now()
                    WHERE id = $1
                    """,
                    job_id,
                )

        logger.info(f"auto_tess: claimed job={job_id} file={file_id}")

        input_spec = TessInputSpec.from_dict(
            input_spec_raw if isinstance(input_spec_raw, dict)
            else json.loads(input_spec_raw) if input_spec_raw else {}
        )

        # Download the STEP file from storage.
        storage = self.storage_getter()
        try:
            rc = await storage.get(storage_key)
            step_bytes = await rc.read()
            await rc.close()
        except Exception as e:
            logger.error(f"auto_tess: download step failed (job={job_id}): {e}")
            await self.mark_error("step_tessellation_jobs", job_id, f"download step: {e}")
            return True

        if not step_bytes:
            await self.mark_error("step_tessellation_jobs", job_id, "empty step file")
            return True

        # Run tessellation via pyworker.
        try:
            async with asyncio.timeout(self.timeout):
                result = await self.driver.run_tess(step_bytes, input_spec)
        except asyncio.TimeoutError:
            await self.mark_error("step_tessellation_jobs", job_id, "tessellation timeout")
            return True
        except Exception as e:
            logger.error(f"auto_tess: job={job_id} tess failed: {e}")
            await self.mark_error("step_tessellation_jobs", job_id, str(e))
            return True

        # Persist result and update files.mesh_storage_key.
        mesh_key = result.output_key or ""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE step_tessellation_jobs
                        SET status = 'done', mesh_storage_key = $2,
                            finished_at = now(), error = null
                        WHERE id = $1
                        """,
                        job_id,
                        mesh_key,
                    )
                    if mesh_key:
                        await conn.execute(
                            "UPDATE files SET mesh_storage_key = $2 WHERE id = $1",
                            file_id,
                            mesh_key,
                        )
        except Exception as e:
            logger.exception(f"auto_tess: mark-done failed (job={job_id}): {e}")
            await self.mark_error("step_tessellation_jobs", job_id, f"mark done: {e}")
            return True

        logger.info(f"auto_tess: job={job_id} file={file_id} done mesh={mesh_key}")
        return True

    # -------------------------------------------------------------------------
    # PG LISTEN/NOTIFY helpers
    # -------------------------------------------------------------------------

    async def _listen_notify(self) -> None:
        """
        Coroutine that listens for PG NOTIFY events on the ``step_file_uploaded``
        channel on a dedicated connection. When a notification is received,
        ``_notify_event.set()`` is called to wake up the worker loop.
        """
        while not self._shutdown:
            try:
                async with self.pool.acquire() as conn:
                    await conn.add_listener(
                        "step_file_uploaded",
                        lambda *args: self._notify_event.set(),
                    )
                    await self._notify_event.wait()
                    self._notify_event.clear()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("auto_tess: listen_notify error, retrying in 5s")
                await asyncio.sleep(5.0)
