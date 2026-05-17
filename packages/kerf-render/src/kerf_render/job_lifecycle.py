"""kerf-render: Postgres-backed render-job lifecycle helpers.

Provides :func:`submit_job`, :func:`get_job_status`, and
:func:`cancel_job` that operate on the ``render_jobs`` table created
by migration ``065_render_jobs.sql``.

All three functions are ``async`` and accept an ``asyncpg`` connection
or pool as their first argument, following the same pattern used by the
rest of the kerf-workers harness.

Table schema (abbreviated)::

    render_jobs (
        id              uuid PRIMARY KEY,
        user_id         uuid,
        scene_blob_hash text,
        preset          text,
        status          text,       -- queued | rendering | complete | failed | cancelled
        samples_done    int,
        samples_total   int,
        signed_url      text,
        error           text,
        created_at      timestamptz,
        updated_at      timestamptz
    )
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from kerf_render.cycles_worker import PRESET_SAMPLES


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


async def submit_job(
    pool,
    *,
    user_id: str,
    scene_blob_hash: str,
    preset: str = "standard",
    output_format: str = "png",
    job_id: Optional[str] = None,
) -> str:
    """Insert a new render job row with ``status='queued'``.

    Parameters
    ----------
    pool:
        An ``asyncpg.Pool`` (or connection) with a ``execute`` / ``fetchrow``
        interface.
    user_id:
        The UUID of the requesting user as a string.
    scene_blob_hash:
        SHA-256 hex of the scene blob (computed by the caller via
        :func:`kerf_render.cycles_worker.compute_cache_key` or equivalent).
    preset:
        Quality preset name (``"draft"``, ``"standard"``, ``"hero"``,
        ``"cinema"``).  Defaults to ``"standard"``.
    output_format:
        ``"png"`` or ``"exr"``.
    job_id:
        Optional explicit UUID string for the job.  A new UUID is generated
        when not supplied.

    Returns
    -------
    str
        The job UUID as a string.
    """
    if preset not in PRESET_SAMPLES:
        preset = "standard"

    jid = job_id or str(uuid.uuid4())
    samples_total = PRESET_SAMPLES[preset]

    await pool.execute(
        """
        INSERT INTO render_jobs
            (id, user_id, scene_blob_hash, preset, status,
             samples_done, samples_total, created_at, updated_at)
        VALUES
            ($1, $2, $3, $4, 'queued',
             0, $5, now(), now())
        """,
        jid,
        user_id,
        scene_blob_hash,
        preset,
        samples_total,
    )

    return jid


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def get_job_status(pool, job_id: str) -> Optional[Dict[str, Any]]:
    """Return the current status of a render job as a dict, or ``None``.

    The returned dict mirrors the ``render_jobs`` column set::

        {
            "id":              str,
            "user_id":         str,
            "scene_blob_hash": str,
            "preset":          str,
            "status":          str,
            "samples_done":    int,
            "samples_total":   int,
            "signed_url":      str | None,
            "error":           str | None,
            "created_at":      datetime | str,
            "updated_at":      datetime | str,
        }

    Returns ``None`` when no row is found for ``job_id``.
    """
    row = await pool.fetchrow(
        """
        SELECT id, user_id, scene_blob_hash, preset, status,
               samples_done, samples_total, signed_url, error,
               created_at, updated_at
        FROM render_jobs
        WHERE id = $1
        """,
        job_id,
    )
    if row is None:
        return None

    return {
        "id":              str(row["id"]),
        "user_id":         str(row["user_id"]) if row["user_id"] else None,
        "scene_blob_hash": row["scene_blob_hash"],
        "preset":          row["preset"],
        "status":          row["status"],
        "samples_done":    row["samples_done"],
        "samples_total":   row["samples_total"],
        "signed_url":      row["signed_url"],
        "error":           row["error"],
        "created_at":      row["created_at"],
        "updated_at":      row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def cancel_job(pool, job_id: str) -> bool:
    """Cancel a queued or rendering job.

    Sets ``status = 'cancelled'`` and clears any error.  Jobs that are
    already in a terminal state (``complete``, ``failed``, ``cancelled``)
    are not modified.

    Returns
    -------
    bool
        ``True`` if the row was updated, ``False`` if nothing changed (job
        not found, or already in a terminal state).
    """
    result = await pool.execute(
        """
        UPDATE render_jobs
        SET status = 'cancelled', updated_at = now(), error = null
        WHERE id = $1
          AND status NOT IN ('complete', 'failed', 'cancelled')
        """,
        job_id,
    )
    # asyncpg returns "UPDATE N" as a string; extract the row count.
    try:
        count = int(str(result).split()[-1])
    except (IndexError, ValueError):
        count = 0
    return count > 0


# ---------------------------------------------------------------------------
# Internal lifecycle helpers (used by CyclesWorker integration)
# ---------------------------------------------------------------------------


async def mark_rendering(pool, job_id: str, samples_total: int) -> None:
    """Transition a job from ``queued`` → ``rendering``."""
    await pool.execute(
        """
        UPDATE render_jobs
        SET status = 'rendering', samples_total = $2, updated_at = now()
        WHERE id = $1
        """,
        job_id,
        samples_total,
    )


async def update_progress(pool, job_id: str, samples_done: int) -> None:
    """Update ``samples_done`` for a rendering job."""
    await pool.execute(
        """
        UPDATE render_jobs
        SET samples_done = $2, updated_at = now()
        WHERE id = $1
        """,
        job_id,
        samples_done,
    )


async def mark_complete(pool, job_id: str, signed_url: str) -> None:
    """Transition a job to ``complete`` and store the result URL."""
    await pool.execute(
        """
        UPDATE render_jobs
        SET status = 'complete', signed_url = $2,
            samples_done = samples_total,
            updated_at = now(), error = null
        WHERE id = $1
        """,
        job_id,
        signed_url,
    )


async def mark_failed(pool, job_id: str, error: str) -> None:
    """Transition a job to ``failed`` and record the error string."""
    await pool.execute(
        """
        UPDATE render_jobs
        SET status = 'failed', error = $2, updated_at = now()
        WHERE id = $1
        """,
        job_id,
        error[:2000] if len(error) > 2000 else error,
    )


__all__ = [
    "submit_job",
    "get_job_status",
    "cancel_job",
    "mark_rendering",
    "update_progress",
    "mark_complete",
    "mark_failed",
]
