"""kerf-render: CyclesQueueWorker — BaseWorker adapter for render_jobs.

Bridges the generic :class:`~kerf_workers.base.BaseWorker` poll-loop with
:class:`~kerf_render.cycles_worker.CyclesWorker`.

The ``render_jobs`` table has a different schema from the ``*_jobs`` tables
expected by ``BaseWorker.claim_job`` (no ``file_id`` FK), so we implement
``run_one`` directly with a custom ``FOR UPDATE SKIP LOCKED`` query.

Job schema stored in render_jobs
---------------------------------
::

    {
        "id":              uuid,
        "user_id":         uuid | null,
        "scene_blob_hash": text,
        "preset":          text,        # draft | standard | hero | cinema
        "status":          text,        # queued | rendering | complete | failed | cancelled
        "payload_json":    jsonb | null, # full job dict (scene_blob, camera, lights, …)
        "samples_done":    int,
        "samples_total":   int,
        "signed_url":      text | null,
        "error":           text | null,
        "created_at":      timestamptz,
        "updated_at":      timestamptz,
    }

``payload_json`` is populated by the async POST /run-render route and contains
the full job dict consumed by :meth:`CyclesWorker.process_job`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from kerf_workers.base import BaseWorker
from kerf_render.cycles_worker import CyclesWorker, CyclesWorkerConfig, resolve_blender_bin
from kerf_render.job_lifecycle import mark_complete, mark_failed, mark_rendering, update_progress

logger = logging.getLogger(__name__)


class CyclesQueueWorker(BaseWorker):
    """Poll the ``render_jobs`` table and execute pending Cycles renders.

    Parameters
    ----------
    pool:
        An ``asyncpg.Pool`` connected to the Kerf Postgres database.
    poll_interval:
        Seconds to wait between queue polls when no job is found.
    config:
        Optional :class:`~kerf_render.cycles_worker.CyclesWorkerConfig`.
        Defaults are used when not supplied.
    """

    def __init__(
        self,
        pool,
        poll_interval: float = 5.0,
        config: Optional[CyclesWorkerConfig] = None,
    ) -> None:
        super().__init__("cycles_queue_worker", pool, poll_interval)
        cfg = config or CyclesWorkerConfig(blender_path=resolve_blender_bin())
        self._worker = CyclesWorker(cfg)

    async def run_one(self) -> bool:
        """Claim one queued render job and execute it.

        Returns ``True`` if a job was processed (whether success or failure),
        ``False`` if the queue was empty.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, preset, payload_json
                    FROM render_jobs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                if row is None:
                    return False

                job_id = str(row["id"])
                preset = row["preset"] or "standard"
                payload_raw = row["payload_json"]

                # Mark as rendering immediately inside the transaction so no
                # other worker claims the same row.
                await conn.execute(
                    """
                    UPDATE render_jobs
                    SET status = 'rendering', updated_at = now()
                    WHERE id = $1
                    """,
                    job_id,
                )

        # --- Deserialise payload -------------------------------------------
        if payload_raw is None:
            payload: dict = {}
        elif isinstance(payload_raw, str):
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = dict(payload_raw)  # asyncpg may return a Record/dict

        payload.setdefault("preset", preset)
        payload.setdefault("job_id", job_id)

        # --- Progress bridge -----------------------------------------------
        async def _progress(event: dict) -> None:
            """Forward tile events to the DB progress column (best-effort)."""
            done = int(event.get("samples_done", 0))
            try:
                await update_progress(self.pool, job_id, done)
            except Exception:
                pass  # progress update failures are non-fatal

        # Build a sync callback that schedules the async update.
        loop = asyncio.get_event_loop()

        def sync_progress(event: dict) -> None:
            asyncio.run_coroutine_threadsafe(_progress(event), loop)

        # --- Execute in thread pool so the event loop stays responsive ------
        logger.info("cycles_queue_worker: starting job=%s preset=%s", job_id, preset)
        try:
            result = await asyncio.to_thread(
                self._worker.process_job,
                payload,
                progress_callback=sync_progress,
            )
        except Exception as exc:
            logger.exception("cycles_queue_worker: job=%s raised exception", job_id)
            await mark_failed(self.pool, job_id, str(exc))
            return True

        # --- Persist outcome -----------------------------------------------
        if result.get("ok"):
            signed_url = result.get("signed_url", "")
            await mark_complete(self.pool, job_id, signed_url)
            logger.info(
                "cycles_queue_worker: job=%s complete url=%s seconds=%.1f",
                job_id, signed_url, result.get("render_seconds", 0.0),
            )
        else:
            reason = result.get("reason", "unknown")
            stderr = result.get("stderr_tail", "")
            error_msg = f"{reason}\n{stderr}"[:2000]
            await mark_failed(self.pool, job_id, error_msg)
            logger.error(
                "cycles_queue_worker: job=%s failed reason=%s", job_id, reason
            )

        return True


__all__ = ["CyclesQueueWorker"]
